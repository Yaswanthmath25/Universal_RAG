from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException,
    Depends,
    Form,
)

from pathlib import Path
import uuid

from backend.services.document_processor import extract_document_text
from backend.services.chunking import chunk_document
from backend.services.embedding_service import generate_embeddings

from backend.services.vector_store import (
    store_chunks,
    replace_document_vectors,
    get_collection_count,
    delete_document_vectors,
)

from backend.database import SessionLocal
from backend.models import Document, DocumentVersion

from backend.services.auth_dependencies import (
    require_admin,
    require_admin_or_customer,
)


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt", ".csv", ".xlsx"]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def resolve_access_scope(file_type, requested_scope):

    if requested_scope in ("company_policy", "user_data", "shared"):
        return requested_scope

    if file_type in (".csv", ".xlsx"):
        return "user_data"

    return "company_policy"


async def process_document(file, access_scope, target_user_id):

    original_filename = file.filename or "unknown"
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Only PDF, DOCX, TXT, CSV and XLSX files are allowed"
        )

    if access_scope == "user_data" and not target_user_id:
        raise ValueError(
            "user_data documents must be associated with a target_user_id"
        )

    if access_scope == "company_policy" and target_user_id:
        raise ValueError(
            "company_policy documents must NOT have a target_user_id"
        )

    unique_filename = f"{uuid.uuid4()}{extension}"
    document_id = Path(unique_filename).stem
    file_path = UPLOAD_DIR / unique_filename

    vectors_stored = False
    db = SessionLocal()

    try:
        content = await file.read()
        if not content:
            raise ValueError("Uploaded file is empty")

        file_path.write_bytes(content)

        extracted_data = extract_document_text(file_path)
        if not extracted_data:
            raise ValueError("No readable text found")

        chunks = chunk_document(extracted_data, original_filename)
        if not chunks:
            raise ValueError("No text chunks were generated")

        embeddings = generate_embeddings(chunks)

        stored_count = store_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=document_id,
            access_scope=access_scope,
            target_user_id=target_user_id,
        )
        vectors_stored = True

        new_document = Document(
            id=document_id,
            filename=original_filename,
            file_type=extension,
            file_path=str(file_path),
            total_chunks=stored_count,
            version_number=1,
            access_scope=access_scope,
            target_user_id=target_user_id,
        )

        db.add(new_document)
        db.commit()

        return {
            "document_id": document_id,
            "original_filename": original_filename,
            "saved_filename": unique_filename,
            "version_number": 1,
            "access_scope": access_scope,
            "target_user_id": target_user_id,
            "sections_extracted": len(extracted_data),
            "total_chunks": len(chunks),
            "stored_chunks": stored_count,
            "status": "Success",
        }

    except Exception:
        db.rollback()
        if vectors_stored:
            delete_document_vectors(document_id)
        if file_path.exists():
            file_path.unlink()
        raise

    finally:
        db.close()


# --------------------------------------------------
# 1. UPLOAD SINGLE DOCUMENT (ADMIN ONLY)
# --------------------------------------------------

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    access_scope: str = Form(default=None),
    target_user_id: str = Form(default=None),
    current_user: dict = Depends(require_admin),
):
    try:
        extension = Path(file.filename or "").suffix.lower()
        resolved_scope = resolve_access_scope(extension, access_scope)

        result = await process_document(
            file=file,
            access_scope=resolved_scope,
            target_user_id=target_user_id,
        )

        return {
            "message": "Document successfully stored",
            **result,
            "total_vectors_in_database": get_collection_count(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"Document processing failed: {str(error)}",
        )


# --------------------------------------------------
# 2. UPLOAD MULTIPLE DOCUMENTS (ADMIN ONLY)
# --------------------------------------------------

@router.post("/upload-multiple")
async def upload_multiple_documents(
    files: list[UploadFile] = File(...),
    access_scope: str = Form(default=None),
    target_user_id: str = Form(default=None),
    current_user: dict = Depends(require_admin),
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one document",
        )

    results = []

    for file in files:
        try:
            extension = Path(file.filename or "").suffix.lower()
            resolved_scope = resolve_access_scope(extension, access_scope)

            result = await process_document(
                file=file,
                access_scope=resolved_scope,
                target_user_id=target_user_id,
            )
            results.append(result)

        except Exception as error:
            results.append({
                "original_filename": file.filename,
                "status": "Failed",
                "message": str(error),
            })

    successful_uploads = sum(
        1 for item in results if item["status"] == "Success"
    )
    failed_uploads = len(results) - successful_uploads

    return {
        "message": "Multiple document upload processing completed",
        "total_files": len(files),
        "successful_uploads": successful_uploads,
        "failed_uploads": failed_uploads,
        "results": results,
        "total_vectors_in_database": get_collection_count(),
    }


# --------------------------------------------------
# 3. LIST DOCUMENTS
#    Admin    -> everything
#    Customer -> ONLY their own user_data documents
# --------------------------------------------------

@router.get("/list")
def list_documents(
    current_user: dict = Depends(require_admin_or_customer),
):
    db = SessionLocal()

    try:
        role = current_user.get("role")
        user_id = current_user.get("id")

        query = db.query(Document)

        if role != "admin":
            # Customer sees ONLY their own user_data — no policies, no shared
            query = query.filter(
                (Document.access_scope == "user_data")
                & (Document.target_user_id == user_id)
            )

        documents = query.order_by(Document.upload_date.desc()).all()

        return {
            "total_documents": len(documents),
            "documents": [
                {
                    "id": d.id,
                    "document_id": d.id,
                    "filename": d.filename,
                    "file_type": d.file_type,
                    "total_chunks": d.total_chunks,
                    "version_number": d.version_number,
                    "access_scope": d.access_scope,
                    "target_user_id": d.target_user_id,
                    "upload_date": d.upload_date,
                }
                for d in documents
            ],
        }

    finally:
        db.close()


# --------------------------------------------------
# 4. UPDATE / REPLACE DOCUMENT (ADMIN ONLY)
# --------------------------------------------------

@router.put("/update/{document_id}")
async def update_document(
    document_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin),
):
    db = SessionLocal()
    new_file_path = None

    try:
        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        original_filename = file.filename or "unknown"
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Only PDF, DOCX, TXT, CSV and XLSX files are allowed",
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        unique_filename = f"{uuid.uuid4()}{extension}"
        new_file_path = UPLOAD_DIR / unique_filename
        new_file_path.write_bytes(content)

        extracted_data = extract_document_text(new_file_path)
        if not extracted_data:
            raise HTTPException(
                status_code=400,
                detail="No readable text found in replacement document",
            )

        chunks = chunk_document(extracted_data, original_filename)
        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No text chunks were generated",
            )

        embeddings = generate_embeddings(chunks)

        previous_version_number = document.version_number or 1

        version_record = DocumentVersion(
            id=str(uuid.uuid4()),
            document_id=document.id,
            version_number=previous_version_number,
            filename=document.filename,
            file_type=document.file_type,
            file_path=document.file_path,
        )
        db.add(version_record)

        stored_count = replace_document_vectors(
            chunks=chunks,
            embeddings=embeddings,
            document_id=document_id,
            access_scope=document.access_scope,
            target_user_id=document.target_user_id,
        )

        old_file_path = Path(document.file_path)

        document.filename = original_filename
        document.file_type = extension
        document.file_path = str(new_file_path)
        document.total_chunks = stored_count
        document.version_number = previous_version_number + 1

        db.commit()

        if old_file_path.exists() and old_file_path != new_file_path:
            old_file_path.unlink()

        return {
            "message": "Document replaced successfully",
            "document_id": document_id,
            "filename": original_filename,
            "saved_filename": unique_filename,
            "previous_version": previous_version_number,
            "current_version": document.version_number,
            "access_scope": document.access_scope,
            "target_user_id": document.target_user_id,
            "sections_extracted": len(extracted_data),
            "total_chunks": len(chunks),
            "stored_chunks": stored_count,
            "total_vectors_in_database": get_collection_count(),
            "status": "Success",
        }

    except HTTPException:
        db.rollback()
        if new_file_path and new_file_path.exists():
            new_file_path.unlink()
        raise

    except Exception as error:
        db.rollback()
        if new_file_path and new_file_path.exists():
            new_file_path.unlink()
        raise HTTPException(
            status_code=500,
            detail=f"Document update failed: {str(error)}",
        )

    finally:
        db.close()


# --------------------------------------------------
# 5. GET DOCUMENT VERSION HISTORY (ADMIN ONLY)
# --------------------------------------------------

@router.get("/history/{document_id}")
def get_document_version_history(
    document_id: str,
    current_user: dict = Depends(require_admin),
):
    db = SessionLocal()

    try:
        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        previous_versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .all()
        )

        history = [
            {
                "version_number": v.version_number,
                "filename": v.filename,
                "file_type": v.file_type,
                "replaced_at": v.replaced_at,
                "file_path": v.file_path,
            }
            for v in previous_versions
        ]

        return {
            "document_id": document.id,
            "current_version": document.version_number,
            "current_filename": document.filename,
            "total_previous_versions": len(history),
            "history": history,
        }

    finally:
        db.close()


# --------------------------------------------------
# 6. DELETE DOCUMENT (ADMIN ONLY)
# --------------------------------------------------

@router.delete("/delete/{document_id}")
def delete_document(
    document_id: str,
    current_user: dict = Depends(require_admin),
):
    db = SessionLocal()

    try:
        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = Path(document.file_path)

        db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id
        ).delete(synchronize_session=False)

        deleted_chunks = delete_document_vectors(document_id)

        if file_path.exists():
            file_path.unlink()

        db.delete(document)
        db.commit()

        return {
            "message": "Document deleted successfully",
            "document_id": document_id,
            "deleted_chunks": deleted_chunks,
            "remaining_vectors": get_collection_count(),
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Document deletion failed: {str(error)}",
        )

    finally:
        db.close()


# --------------------------------------------------
# 7. GET SINGLE DOCUMENT DETAILS
#    Customer -> 403 unless it is their own user_data
# --------------------------------------------------

@router.get("/{document_id}")
def get_document_details(
    document_id: str,
    current_user: dict = Depends(require_admin_or_customer),
):
    db = SessionLocal()

    try:
        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        role = current_user.get("role")
        user_id = current_user.get("id")

        if role != "admin":
            # Customer must not be able to inspect any policy/shared doc,
            # nor another customer's user_data doc.
            if (
                document.access_scope != "user_data"
                or document.target_user_id != user_id
            ):
                raise HTTPException(status_code=403, detail="Access denied")

        return {
            "document_id": document.id,
            "filename": document.filename,
            "file_type": document.file_type,
            "total_chunks": document.total_chunks,
            "version_number": document.version_number,
            "access_scope": document.access_scope,
            "target_user_id": document.target_user_id,
            "upload_date": document.upload_date,
        }

    finally:
        db.close()