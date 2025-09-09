"""
ChunkVault Web Interface
Professional file storage and management system
"""
import streamlit as st
import requests
import io
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
STORAGE_NODES = [
    "http://localhost:8001",
    "http://localhost:8002", 
    "http://localhost:8003"
]

# Page configuration
st.set_page_config(
    page_title="ChunkVault",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional look
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 600;
        color: #1f2937;
        text-align: center;
        margin-bottom: 2rem;
        border-bottom: 3px solid #3b82f6;
        padding-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .success-message {
        background-color: #d1fae5;
        color: #065f46;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #10b981;
        margin: 1rem 0;
    }
    .error-message {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
        margin: 1rem 0;
    }
    .file-card {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        background-color: #f9fafb;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        transition: box-shadow 0.2s;
    }
    .file-card:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    }
    .sidebar .sidebar-content {
        background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
    }
    .upload-area {
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        background-color: #f8fafc;
        margin: 1rem 0;
    }
    .upload-area:hover {
        border-color: #3b82f6;
        background-color: #eff6ff;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None

def make_api_request(method: str, endpoint: str, data: Dict = None, files: Dict = None) -> Optional[Dict]:
    """Make API request with authentication"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {}
    
    if st.session_state.access_token:
        headers["Authorization"] = f"Bearer {st.session_state.access_token}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            if files:
                response = requests.post(url, headers=headers, files=files)
            else:
                response = requests.post(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"Connection Error: {str(e)}")
        return None

def login_user(username: str, password: str) -> bool:
    """Login user and store token"""
    data = {"username": username, "password": password}
    response = make_api_request("POST", "/auth/login", data)
    
    if response:
        st.session_state.access_token = response["access_token"]
        st.session_state.user_id = response["user_id"]
        st.session_state.username = username
        return True
    return False

def register_user(username: str, email: str, password: str) -> bool:
    """Register new user"""
    data = {"username": username, "email": email, "password": password}
    response = make_api_request("POST", "/auth/register", data)
    return response is not None

def logout_user():
    """Logout user"""
    st.session_state.access_token = None
    st.session_state.user_id = None
    st.session_state.username = None

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def get_storage_stats() -> Dict:
    """Get storage node statistics"""
    stats = {"total_size": 0, "total_chunks": 0, "available_space": 0}
    
    for node_url in STORAGE_NODES:
        try:
            response = requests.get(f"{node_url}/storage/stats", timeout=5)
            if response.status_code == 200:
                node_stats = response.json()["storage_stats"]
                stats["total_size"] += node_stats["total_size"]
                stats["total_chunks"] += node_stats["chunk_count"]
                stats["available_space"] += node_stats["available_space"]
        except:
            continue
    
    return stats

# Main App
def main():
    # Header
    st.markdown('<h1 class="main-header">ChunkVault</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; font-size: 1.1rem; color: #6b7280; margin-bottom: 2rem;">Professional File Storage and Management System</p>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## Authentication")
        
        if st.session_state.access_token:
            st.success(f"Logged in as: **{st.session_state.username}**")
            if st.button("Logout", type="secondary"):
                logout_user()
                st.rerun()
        else:
            # Login/Register tabs
            tab1, tab2 = st.tabs(["Login", "Register"])
            
            with tab1:
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    login_btn = st.form_submit_button("Login", type="primary")
                    
                    if login_btn:
                        if login_user(username, password):
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Login failed!")
            
            with tab2:
                with st.form("register_form"):
                    reg_username = st.text_input("Username", key="reg_username")
                    reg_email = st.text_input("Email", key="reg_email")
                    reg_password = st.text_input("Password", type="password", key="reg_password")
                    reg_btn = st.form_submit_button("Register", type="primary")
                    
                    if reg_btn:
                        if register_user(reg_username, reg_email, reg_password):
                            st.success("Registration successful! Please login.")
                        else:
                            st.error("Registration failed!")
    
    # Main content
    if not st.session_state.access_token:
        st.info("Please login to access ChunkVault features.")
        
        # Show system overview for non-authenticated users
        st.markdown("## System Overview")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Storage Nodes", len(STORAGE_NODES))
        
        with col2:
            stats = get_storage_stats()
            st.metric("Total Storage", format_file_size(stats["total_size"]))
        
        with col3:
            st.metric("Available Space", format_file_size(stats["available_space"]))
        
        with col4:
            st.metric("Total Chunks", stats["total_chunks"])
        
        # Storage distribution
        if stats["total_size"] > 0:
            st.markdown("### Storage Distribution")
            used_percent = (stats["total_size"] / (stats["total_size"] + stats["available_space"])) * 100
            st.progress(used_percent / 100)
            st.write(f"Used: {format_file_size(stats['total_size'])} ({used_percent:.1f}%)")
            st.write(f"Available: {format_file_size(stats['available_space'])} ({100-used_percent:.1f}%)")
        
        return
    
    # Authenticated user interface
    st.markdown(f"Welcome back, **{st.session_state.username}**!")
    
    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Files", "Upload", "Analytics", "Settings"])
    
    with tab1:
        st.markdown("## Your Files")
        
        # Refresh button
        if st.button("Refresh", type="secondary"):
            st.rerun()
        
        # Get user files
        files = make_api_request("GET", "/files")
        
        if files:
            if len(files) == 0:
                st.info("No files found. Upload your first file!")
            else:
                # File statistics
                total_size = sum(file["size"] for file in files)
                st.metric("Total Files", len(files))
                st.metric("Total Size", format_file_size(total_size))
                
                # Files list
                for file in files:
                    with st.container():
                        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
                        
                        with col1:
                            st.write(f"**{file['filename']}**")
                            st.caption(f"Uploaded: {datetime.fromisoformat(file['created_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')}")
                        
                        with col2:
                            st.write(format_file_size(file['size']))
                        
                        with col3:
                            status_color = "🟢" if file['status'] == 'completed' else "🟡" if file['status'] == 'uploading' else "🔴"
                            st.write(f"{status_color} {file['status']}")
                        
                        with col4:
                            if st.button("Download", key=f"download_{file['id']}"):
                                with st.spinner("Downloading..."):
                                    response = requests.get(
                                        f"{API_BASE_URL}/files/{file['id']}/download",
                                        headers={"Authorization": f"Bearer {st.session_state.access_token}"}
                                    )
                                    if response.status_code == 200:
                                        st.download_button(
                                            "Save File",
                                            response.content,
                                            file_name=file['filename'],
                                            mime=file['mime_type']
                                        )
                        
                        with col5:
                            if st.button("Share", key=f"share_{file['id']}"):
                                with st.spinner("Creating share link..."):
                                    share_data = {"expires_in_hours": 24}
                                    share_response = make_api_request("POST", f"/files/{file['id']}/share", share_data)
                                    if share_response:
                                        st.success(f"Share link created: {share_response['share_url']}")
                                        st.code(share_response['share_url'])
                        
                        st.divider()
        else:
            st.error("Failed to load files.")
    
    with tab2:
        st.markdown("## Upload File")
        
        uploaded_file = st.file_uploader(
            "Choose a file to upload",
            type=None,  # Allow all file types
            help="Select any file to upload to ChunkVault"
        )
        
        if uploaded_file is not None:
            # File info
            st.info(f"**File:** {uploaded_file.name}")
            st.info(f"**Size:** {format_file_size(uploaded_file.size)}")
            st.info(f"**Type:** {uploaded_file.type}")
            
            if st.button("Upload to ChunkVault", type="primary"):
                with st.spinner("Uploading file..."):
                    # Prepare file for upload
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    
                    # Upload file
                    response = make_api_request("POST", "/files/upload", files=files)
                    
                    if response:
                        st.success("File uploaded successfully!")
                        st.json(response)
                    else:
                        st.error("Upload failed!")
    
    with tab3:
        st.markdown("## Analytics")
        
        # System metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Storage Nodes", len(STORAGE_NODES))
        
        with col2:
            stats = get_storage_stats()
            st.metric("Total Storage", format_file_size(stats["total_size"]))
        
        with col3:
            st.metric("Available Space", format_file_size(stats["available_space"]))
        
        with col4:
            st.metric("Total Chunks", stats["total_chunks"])
        
        # User files analytics
        files = make_api_request("GET", "/files")
        if files:
            # File size distribution
            file_sizes = [file["size"] for file in files]
            if file_sizes:
                st.markdown("### File Size Distribution")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Smallest File", format_file_size(min(file_sizes)))
                with col2:
                    st.metric("Largest File", format_file_size(max(file_sizes)))
                with col3:
                    avg_size = sum(file_sizes) / len(file_sizes)
                    st.metric("Average Size", format_file_size(int(avg_size)))
            
            # File types
            file_types = {}
            for file in files:
                mime_type = file["mime_type"]
                file_type = mime_type.split('/')[0] if '/' in mime_type else 'unknown'
                file_types[file_type] = file_types.get(file_type, 0) + 1
            
            if file_types:
                st.markdown("### File Types Distribution")
                for file_type, count in file_types.items():
                    st.write(f"**{file_type}**: {count} files")
    
    with tab4:
        st.markdown("## Settings")
        
        st.markdown("### System Configuration")
        st.info(f"**API Base URL:** {API_BASE_URL}")
        st.info(f"**Storage Nodes:** {len(STORAGE_NODES)}")
        
        st.markdown("### Storage Nodes Status")
        for i, node_url in enumerate(STORAGE_NODES, 1):
            try:
                response = requests.get(f"{node_url}/health", timeout=5)
                if response.status_code == 200:
                    st.success(f"Node {i}: Healthy")
                else:
                    st.error(f"Node {i}: Unhealthy")
            except:
                st.error(f"Node {i}: Offline")
        
        st.markdown("### Account Management")
        if st.button("Delete Account", type="secondary"):
            st.warning("Account deletion not implemented yet.")

if __name__ == "__main__":
    main()