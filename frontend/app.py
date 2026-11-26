
import streamlit as st
import requests
import html
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="NexaMart AI Support",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "http://127.0.0.1:8000"
API_TIMEOUT = 30
AI_TIMEOUT = 300
UPLOAD_TIMEOUT = 300

OUT_OF_CONTEXT_MESSAGE = (
    "I'm sorry, but I couldn't find information related to your "
    "request within the information you're authorized to access. "
    "I can only help with your own account and order-related queries."
)


# ============================================================
# STYLING
# ============================================================

st.html("""
<style>
    .stApp {
        background: #f5f7fb;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1250px;
    }

    .hero {
        background: linear-gradient(120deg, #172554, #1e40af);
        padding: 38px;
        border-radius: 18px;
        color: white;
        margin-bottom: 25px;
    }

    .hero h1 {
        color: white;
        font-size: 36px;
        margin-bottom: 8px;
    }

    .hero p {
        color: #dbeafe;
        font-size: 16px;
    }

    .muted {
        color: #64748b;
        font-size: 14px;
    }

    .login-card {
        background: white;
        padding: 28px;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
    }

    div.stButton > button {
        border-radius: 9px;
        font-weight: 600;
        min-height: 42px;
    }

    [data-testid="stChatMessage"] {
        border-radius: 12px;
    }

    section[data-testid="stSidebar"] {
        background: #ffffff;
    }
</style>
""")


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "token": None,
    "user": None,
    "role": None,
    "page": "home",

    "admin_conversation_id": None,
    "admin_messages": [],

    "customer_conversation_id": None,
    "customer_messages": [],

    "uploaded_document": None,

    "last_api_error": None,
    "last_api_debug": None
}


def initialize_session():
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session()


# ============================================================
# COMMON HELPERS
# ============================================================

def headers(token=None):
    active_token = token or st.session_state.token

    return {
        "Authorization": f"Bearer {active_token}"
    }


def api_error(response):
    try:
        data = response.json()
        detail = data.get("detail", data)
    except Exception:
        detail = response.text

    error_message = (
        f"API Error ({response.status_code}): {detail}"
    )

    st.session_state.last_api_error = error_message

    print("\n========== FRONTEND API ERROR ==========")
    print(error_message)

    st.error(error_message)


def normalize_list(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in [
            "items",
            "results",
            "conversations",
            "messages",
            "history",
            "data",
            "documents"
        ]:
            if isinstance(data.get(key), list):
                return data[key]

    return []


def go_to(page):
    st.session_state.page = page
    st.rerun()


def logout():
    st.session_state.clear()

    for key, value in DEFAULTS.items():
        st.session_state[key] = value


def current_user_name():
    user = st.session_state.user or {}

    return (
        user.get("full_name")
        or user.get("username")
        or user.get("email")
        or "User"
    )


# ============================================================
# AUTHENTICATION
# ============================================================

def authenticate(email, password, expected_role):
    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={
                "email": email,
                "password": password
            },
            timeout=API_TIMEOUT
        )

        if response.status_code != 200:
            api_error(response)
            return

        token = response.json().get("access_token")

        if not token:
            st.error("Login response did not contain an access token.")
            return

        user_response = requests.get(
            f"{API_URL}/auth/me",
            headers=headers(token),
            timeout=API_TIMEOUT
        )

        if user_response.status_code != 200:
            api_error(user_response)
            return

        user = user_response.json()

        if user.get("role") != expected_role:
            st.error(
                f"This account does not have {expected_role} access."
            )
            return

        st.session_state.token = token
        st.session_state.user = user
        st.session_state.role = expected_role

        st.session_state.admin_conversation_id = None
        st.session_state.admin_messages = []

        st.session_state.customer_conversation_id = None
        st.session_state.customer_messages = []

        st.session_state.uploaded_document = None
        st.session_state.page = "dashboard"

        st.rerun()

    except requests.RequestException as error:
        st.error(f"Unable to connect to backend: {error}")


def verify_session():
    if not st.session_state.token:
        return False

    try:
        response = requests.get(
            f"{API_URL}/auth/me",
            headers=headers(),
            timeout=API_TIMEOUT
        )

        if response.status_code == 200:
            user = response.json()
            role = user.get("role")

            if role not in ["admin", "customer"]:
                return False

            st.session_state.user = user
            st.session_state.role = role

            return True

        return False

    except requests.RequestException:
        st.error("Unable to connect to the backend.")
        return False


# ============================================================
# CUSTOMER SIGNUP
# ============================================================

def show_signup():
    st.title("Create Your Account")
    st.caption("Register to access NexaMart customer support.")

    with st.form("signup_form"):
        full_name = st.text_input("Full Name")
        username = st.text_input("Username")
        email = st.text_input("Email Address")
        phone = st.text_input("Phone Number")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input(
            "Confirm Password",
            type="password"
        )

        submitted = st.form_submit_button(
            "Create Account",
            use_container_width=True
        )

    if submitted:
        if not all([
            full_name,
            username,
            email,
            phone,
            password,
            confirm_password
        ]):
            st.warning("Please complete all fields.")

        elif password != confirm_password:
            st.error("Passwords do not match.")

        else:
            try:
                response = requests.post(
                    f"{API_URL}/auth/signup",
                    json={
                        "username": username,
                        "full_name": full_name,
                        "email": email,
                        "phone": phone,
                        "password": password
                    },
                    timeout=API_TIMEOUT
                )

                if response.status_code in [200, 201]:
                    st.success("Account created successfully.")
                    st.info("You can now log in.")
                else:
                    api_error(response)

            except requests.RequestException as error:
                st.error(f"Signup failed: {error}")

    if st.button("Back to Home"):
        go_to("home")


# ============================================================
# LOGIN
# ============================================================

def show_login(role):
    title = "Admin Login" if role == "admin" else "Customer Login"

    st.title(title)
    st.caption("Sign in to continue.")

    with st.form(f"{role}_login_form"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")

        submitted = st.form_submit_button(
            "Sign In",
            use_container_width=True
        )

    if submitted:
        if not email or not password:
            st.warning("Enter your email and password.")
        else:
            authenticate(email, password, role)

    if st.button("Back to Home"):
        go_to("home")


# ============================================================
# DOCUMENT UPLOAD
# ============================================================

def upload_document(uploaded_file):
    try:
        response = requests.post(
            f"{API_URL}/documents/upload",
            headers=headers(),
            files={
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type or "application/octet-stream"
                )
            },
            timeout=UPLOAD_TIMEOUT
        )

        if response.status_code in [200, 201]:
            return response.json()

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Document upload failed: {error}")

    return None


def show_document_upload():
    st.title("Knowledge Base")
    st.caption(
        "Upload company documents and customer information "
        "for the AI assistant."
    )

    st.info(
        "Uploaded documents become available to the admin assistant. "
        "Customer access must be restricted by the backend retrieval "
        "service to the authenticated customer's own records."
    )

    uploaded_file = st.file_uploader(
        "Select a document",
        type=["pdf", "docx", "txt", "csv", "xlsx"],
        help="Supported formats: PDF, DOCX, TXT, CSV and XLSX."
    )

    if uploaded_file:
        st.write(f"**Selected file:** {uploaded_file.name}")
        st.write(
            f"**File size:** {uploaded_file.size / 1024:.2f} KB"
        )

        if st.button(
            "Upload and Process Document",
            type="primary",
            use_container_width=True
        ):
            with st.spinner(
                "Uploading document and processing its content..."
            ):
                result = upload_document(uploaded_file)

            if result is not None:
                st.session_state.uploaded_document = result
                st.success("Document uploaded and processed successfully.")

                st.subheader("Processing Result")
                st.json(result)

    st.divider()

    st.subheader("How document retrieval works")

    st.markdown("""
    1. Admin uploads a document.
    2. The backend extracts the document content.
    3. Content is divided into smaller chunks.
    4. Embeddings are generated and stored in the vector database.
    5. The AI assistant retrieves relevant information when asked.
    """)


# ============================================================
# MANAGE DOCUMENTS
# ============================================================

def get_documents():
    try:
        response = requests.get(
            f"{API_URL}/documents/list",
            headers=headers(),
            timeout=API_TIMEOUT
        )

        if response.status_code == 200:
            return normalize_list(response.json())

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Unable to retrieve documents: {error}")

    return None


def replace_document(document_id, uploaded_file):
    try:
        response = requests.put(
            f"{API_URL}/documents/update/{document_id}",
            headers=headers(),
            files={
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type or "application/octet-stream"
                )
            },
            timeout=UPLOAD_TIMEOUT
        )

        if response.status_code in [200, 201]:
            return True

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Document replacement failed: {error}")

    return False


def remove_document(document_id):
    try:
        response = requests.delete(
            f"{API_URL}/documents/delete/{document_id}",
            headers=headers(),
            timeout=API_TIMEOUT
        )

        if response.status_code in [200, 204]:
            return True

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Document deletion failed: {error}")

    return False


def show_manage_documents():
    st.title("📚 Manage Documents")

    st.caption(
        "View, replace, and delete documents uploaded to the knowledge base."
    )

    if st.button("🔄 Refresh Documents"):
        st.rerun()

    documents = get_documents()

    if documents is None:
        st.warning(
            "Unable to load documents. Check whether the backend "
            "document-list endpoint is available."
        )
        return

    if not documents:
        st.info("No documents found in the knowledge base.")
        return

    st.success(f"Total documents: {len(documents)}")

    for index, document in enumerate(documents, start=1):

        document_id = (
            document.get("id")
            or document.get("document_id")
        )

        filename = (
            document.get("filename")
            or document.get("file_name")
            or document.get("name")
            or f"Document {index}"
        )

        with st.expander(f"📄 {filename}"):

            st.write(f"**Document ID:** {document_id}")

            if document.get("created_at"):
                st.write(
                    f"**Uploaded:** {document.get('created_at')}"
                )

            if document.get("status"):
                st.write(
                    f"**Status:** {document.get('status')}"
                )

            if not document_id:
                st.warning("Document ID is missing.")
                continue

            st.divider()

            st.markdown("**Replace Document**")

            replacement_file = st.file_uploader(
                "Select replacement document",
                type=["pdf", "docx", "txt", "csv", "xlsx"],
                key=f"replace_file_{document_id}"
            )

            if replacement_file:
                if st.button(
                    "Replace Document",
                    key=f"replace_button_{document_id}",
                    use_container_width=True
                ):
                    with st.spinner("Replacing document..."):
                        success = replace_document(
                            document_id,
                            replacement_file
                        )

                    if success:
                        st.success("Document replaced successfully.")
                        st.rerun()

            st.divider()

            st.markdown("**Delete Document**")

            confirm_delete = st.checkbox(
                "I confirm that I want to delete this document.",
                key=f"confirm_delete_{document_id}"
            )

            if st.button(
                "🗑️ Delete Document",
                key=f"delete_button_{document_id}",
                disabled=not confirm_delete,
                use_container_width=True
            ):
                with st.spinner("Deleting document..."):
                    success = remove_document(document_id)

                if success:
                    st.success("Document deleted successfully.")
                    st.rerun()


# ============================================================
# AI RESPONSE HELPERS
# ============================================================

def extract_answer(data):
    if not isinstance(data, dict):
        return str(data)

    answer = (
        data.get("answer")
        or data.get("response")
        or data.get("result")
        or data.get("message")
    )

    if isinstance(answer, dict):
        answer = answer.get("answer", str(answer))

    return str(answer or "No answer was returned.")


def extract_sources(data):
    if not isinstance(data, dict):
        return []

    sources = data.get("sources", [])

    return sources if isinstance(sources, list) else []


def extract_conversation_id(data):
    if not isinstance(data, dict):
        return None

    return (
        data.get("conversation_id")
        or data.get("id")
    )


def display_sources(sources):
    if not sources:
        return

    with st.expander("Sources and references"):
        for index, source in enumerate(sources, 1):
            if not isinstance(source, dict):
                st.write(source)
                continue

            filename = source.get(
                "filename",
                source.get("source", "Unknown document")
            )

            page = source.get("page_number", "N/A")
            chunk = source.get("chunk_number", "N/A")

            st.markdown(f"**Source {index}**")

            st.caption(
                f"Document: {html.escape(str(filename))} | "
                f"Page: {html.escape(str(page))} | "
                f"Chunk: {html.escape(str(chunk))}"
            )


def display_messages(messages):
    for message in messages:
        role = message.get("role", "assistant")
        content = message.get("content", "")

        with st.chat_message(
            "user" if role == "user" else "assistant"
        ):
            st.markdown(content)

            if role == "assistant":
                display_sources(message.get("sources", []))


# ============================================================
# AI CHAT REQUESTS WITH DIAGNOSTICS
# ============================================================

def ask_admin(question):
    st.session_state.last_api_error = None
    st.session_state.last_api_debug = None

    print("\n========== STREAMLIT ADMIN REQUEST ==========")
    print("Endpoint:", f"{API_URL}/qa/search")
    print("Question:", question)
    print(
        "Conversation ID:",
        st.session_state.admin_conversation_id
    )

    try:
        response = requests.post(
            f"{API_URL}/qa/search",
            headers=headers(),
            json={
                "question": question,
                "conversation_id": (
                    st.session_state.admin_conversation_id
                )
            },
            timeout=AI_TIMEOUT
        )

        print("\n========== STREAMLIT ADMIN RESPONSE ==========")
        print("Status code:", response.status_code)
        print("Content type:", response.headers.get("content-type"))
        print("Response body:", response.text)

        st.session_state.last_api_debug = {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "response_body": response.text
        }

        if response.status_code != 200:
            api_error(response)
            return None

        try:
            data = response.json()
        except ValueError as error:
            error_message = (
                f"Backend returned HTTP 200, but the response "
                f"was not valid JSON: {error}. "
                f"Response: {response.text[:2000]}"
            )

            st.session_state.last_api_error = error_message
            print(error_message)
            return None

        if isinstance(data, dict):
            print("Response keys:", list(data.keys()))
            print("Answer exists:", bool(data.get("answer")))
            print("Answer length:", len(str(data.get("answer", ""))))

            if data.get("answer"):
                print("Answer received successfully.")
                return data

            error_message = (
                "The backend returned HTTP 200, but its JSON response "
                "does not contain a usable 'answer' field."
            )

            st.session_state.last_api_error = error_message
            print(error_message)

            return data

        error_message = (
            f"Unexpected response format: {type(data).__name__}"
        )

        st.session_state.last_api_error = error_message
        print(error_message)

        return {
            "answer": str(data),
            "sources": []
        }

    except requests.Timeout as error:
        error_message = (
            f"AI request timed out after {AI_TIMEOUT} seconds: {error}"
        )

        st.session_state.last_api_error = error_message
        print(error_message)

    except requests.RequestException as error:
        error_message = f"AI request failed: {error}"

        st.session_state.last_api_error = error_message
        print(error_message)

    except Exception as error:
        error_message = (
            f"Unexpected frontend error: "
            f"{type(error).__name__}: {error}"
        )

        st.session_state.last_api_error = error_message
        print(error_message)

    return None


def ask_customer(question):
    st.session_state.last_api_error = None
    st.session_state.last_api_debug = None

    print("\n========== STREAMLIT CUSTOMER REQUEST ==========")
    print("Endpoint:", f"{API_URL}/qa/customer-search")
    print("Question:", question)

    try:
        response = requests.post(
            f"{API_URL}/qa/customer-search",
            headers=headers(),
            json={
                "question": question,
                "conversation_id": (
                    st.session_state.customer_conversation_id
                )
            },
            timeout=AI_TIMEOUT
        )

        print("\n========== STREAMLIT CUSTOMER RESPONSE ==========")
        print("Status code:", response.status_code)
        print("Response body:", response.text)

        st.session_state.last_api_debug = {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "response_body": response.text
        }

        if response.status_code != 200:
            api_error(response)
            return None

        try:
            data = response.json()
        except ValueError as error:
            error_message = (
                f"Backend returned invalid JSON: {error}. "
                f"Response: {response.text[:2000]}"
            )

            st.session_state.last_api_error = error_message
            print(error_message)
            return None

        if isinstance(data, dict):
            if data.get("answer"):
                return data

            st.session_state.last_api_error = (
                "HTTP 200 received, but the response has no answer field."
            )

            return data

        return {
            "answer": str(data),
            "sources": []
        }

    except requests.Timeout as error:
        error_message = (
            f"Customer AI request timed out after "
            f"{AI_TIMEOUT} seconds: {error}"
        )

        st.session_state.last_api_error = error_message
        print(error_message)

    except requests.RequestException as error:
        error_message = f"Customer assistant request failed: {error}"

        st.session_state.last_api_error = error_message
        print(error_message)

    except Exception as error:
        error_message = (
            f"Unexpected customer frontend error: "
            f"{type(error).__name__}: {error}"
        )

        st.session_state.last_api_error = error_message
        print(error_message)

    return None


# ============================================================
# CONVERSATION HISTORY
# ============================================================

def get_conversations():
    try:
        response = requests.get(
            f"{API_URL}/qa/conversations",
            headers=headers(),
            timeout=API_TIMEOUT
        )

        if response.status_code == 200:
            return normalize_list(response.json())

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Unable to load conversations: {error}")

    return []


def get_history(conversation_id):
    try:
        response = requests.get(
            f"{API_URL}/qa/history/{conversation_id}",
            headers=headers(),
            timeout=API_TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Unable to load chat history: {error}")

    return None


def delete_history(conversation_id):
    try:
        response = requests.delete(
            f"{API_URL}/qa/history/{conversation_id}",
            headers=headers(),
            timeout=API_TIMEOUT
        )

        if response.status_code in [200, 204]:
            return True

        api_error(response)

    except requests.RequestException as error:
        st.error(f"Unable to delete conversation: {error}")

    return False


def convert_history(history):
    messages = []

    for item in normalize_list(history):
        if not isinstance(item, dict):
            continue

        question = item.get("question")
        answer = item.get("answer")

        if question:
            messages.append({
                "role": "user",
                "content": str(question),
                "sources": []
            })

        if answer:
            messages.append({
                "role": "assistant",
                "content": str(answer),
                "sources": item.get("sources", [])
            })

    return messages


def show_conversation_history(role):
    st.subheader("Chat History")

    if role == "admin":
        conversation_key = "admin_conversation_id"
        messages_key = "admin_messages"
        prefix = "admin"
    else:
        conversation_key = "customer_conversation_id"
        messages_key = "customer_messages"
        prefix = "customer"

    if st.button(
        "＋ New Conversation",
        key=f"{prefix}_new_chat",
        use_container_width=True
    ):
        st.session_state[conversation_key] = None
        st.session_state[messages_key] = []
        st.rerun()

    conversations = get_conversations()

    if not conversations:
        st.caption("No previous conversations.")
        return

    for index, conversation in enumerate(conversations):
        if not isinstance(conversation, dict):
            continue

        conversation_id = conversation.get("conversation_id")

        if not conversation_id:
            continue

        label = (
            conversation.get("last_question")
            or conversation.get("title")
            or f"Conversation {index + 1}"
        )

        with st.container(border=True):
            if st.button(
                str(label)[:45],
                key=f"{prefix}_history_{conversation_id}",
                use_container_width=True
            ):
                history = get_history(conversation_id)

                if history is not None:
                    st.session_state[conversation_key] = conversation_id
                    st.session_state[messages_key] = convert_history(history)
                    st.rerun()

            if st.button(
                "Delete conversation",
                key=f"{prefix}_delete_{conversation_id}",
                use_container_width=True
            ):
                if delete_history(conversation_id):
                    if (
                        st.session_state[conversation_key]
                        == conversation_id
                    ):
                        st.session_state[conversation_key] = None
                        st.session_state[messages_key] = []

                    st.rerun()


# ============================================================
# CHAT INTERFACE
# ============================================================

def process_chat(role, question):
    if role == "admin":
        messages_key = "admin_messages"
        conversation_key = "admin_conversation_id"
        request_function = ask_admin
    else:
        messages_key = "customer_messages"
        conversation_key = "customer_conversation_id"
        request_function = ask_customer

    st.session_state[messages_key].append({
        "role": "user",
        "content": question,
        "sources": []
    })

    with st.spinner("Searching for relevant information..."):
        result = request_function(question)

    if result is not None:
        st.session_state[conversation_key] = (
            extract_conversation_id(result)
            or st.session_state[conversation_key]
        )

        answer = extract_answer(result)

        st.session_state[messages_key].append({
            "role": "assistant",
            "content": answer,
            "sources": extract_sources(result)
        })

        print("\n========== CHAT MESSAGE SAVED ==========")
        print("Role:", role)
        print("Answer length:", len(answer))

    else:
        error_message = (
            st.session_state.last_api_error
            or "No response was received from the backend."
        )

        st.session_state[messages_key].append({
            "role": "assistant",
            "content": (
                "I couldn't process your request right now. "
                "Please try again.\n\n"
                f"**Diagnostic information:** {error_message}"
            ),
            "sources": []
        })

        print("\n========== CHAT REQUEST FAILED ==========")
        print(error_message)


# ============================================================
# ADMIN CHAT
# ============================================================

def show_admin_chat():
    st.title("🤖 Admin AI Assistant")

    st.caption(
        "Ask questions about uploaded customer records, orders, "
        "products, company policies, and internal documents."
    )

    st.info(
        "Admin access: the assistant can retrieve information "
        "across all authorized uploaded documents."
    )

    display_messages(st.session_state.admin_messages)

    question = st.chat_input(
        "Ask anything about the uploaded knowledge base...",
        key="admin_chat_input"
    )

    if question:
        process_chat("admin", question)
        st.rerun()


# ============================================================
# CUSTOMER CHAT
# ============================================================

def show_customer_chat():
    st.title("🤖 Customer Support Assistant")

    st.caption(
        "Ask questions about your own account, orders, payments, "
        "deliveries, and support requests."
    )

    st.info(
        "Your assistant can only provide information you're "
        "authorized to access. Other customers' information and "
        "company-internal information are not available."
    )

    display_messages(st.session_state.customer_messages)

    question = st.chat_input(
        "Ask a question about your account or orders...",
        key="customer_chat_input"
    )

    if question:
        process_chat("customer", question)
        st.rerun()


# ============================================================
# HOME PAGE
# ============================================================

def show_home():
    st.markdown("""
    <div class="hero">
        <h1>🤖 NexaMart AI Support</h1>
        <p>
            Your intelligent document-based customer support platform.
            Get answers through a secure AI assistant.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("Choose your portal")

    admin_col, customer_col = st.columns(2)

    with admin_col:
        with st.container(border=True):
            st.subheader("🛡️ Admin Portal")

            st.write(
                "Upload knowledge documents and retrieve information "
                "across the complete knowledge base."
            )

            if st.button(
                "Admin Sign In",
                type="primary",
                use_container_width=True
            ):
                go_to("admin_login")

    with customer_col:
        with st.container(border=True):
            st.subheader("👤 Customer Portal")

            st.write(
                "Chat with the support assistant to get information "
                "about your own account and orders."
            )

            if st.button(
                "Customer Sign In",
                type="primary",
                use_container_width=True
            ):
                go_to("customer_login")

            if st.button(
                "Create Customer Account",
                use_container_width=True
            ):
                go_to("signup")


# ============================================================
# ADMIN PORTAL
# ============================================================

def show_admin_portal():
    with st.sidebar:
        st.title("🛡️ Admin Portal")

        st.caption(current_user_name())

        st.divider()

        selected = st.radio(
            "Navigation",
            [
                "AI Assistant",
                "Upload Documents",
                "Manage Documents"
            ],
            key="admin_navigation"
        )

        st.divider()

        show_conversation_history("admin")

        st.divider()

        st.button(
            "Logout",
            key="admin_logout",
            use_container_width=True,
            on_click=logout
        )

    if selected == "AI Assistant":
        show_admin_chat()

    elif selected == "Upload Documents":
        show_document_upload()

    elif selected == "Manage Documents":
        show_manage_documents()


# ============================================================
# CUSTOMER PORTAL
# ============================================================

def show_customer_portal():
    with st.sidebar:
        st.title("👤 Customer Portal")

        st.caption(current_user_name())

        st.divider()

        st.markdown("**Navigation**")
        st.markdown("💬 Customer Support Chat")

        st.divider()

        show_conversation_history("customer")

        st.divider()

        st.button(
            "Logout",
            key="customer_logout",
            use_container_width=True,
            on_click=logout
        )

    show_customer_chat()


# ============================================================
# APPLICATION ROUTER
# ============================================================

def main():
    page = st.session_state.page

    if page == "home":
        show_home()

    elif page == "signup":
        show_signup()

    elif page == "admin_login":
        show_login("admin")

    elif page == "customer_login":
        show_login("customer")

    elif page == "dashboard":
        if not st.session_state.token:
            go_to("home")
            return

        if not verify_session():
            logout()
            st.rerun()
            return

        if st.session_state.role == "admin":
            show_admin_portal()

        elif st.session_state.role == "customer":
            show_customer_portal()

        else:
            logout()
            st.rerun()

    else:
        go_to("home")


if __name__ == "__main__":
    main()
