"""
Streamlit UI 스타일 정의
"""

APP_STYLES = """
    <style>
    /* 전체 페이지 폰트 설정 */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* 메인 헤더 스타일 */
    h1 {
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        margin-bottom: 0.5rem !important;
        color: #ffffff !important;
    }
    
    /* 서브헤더 스타일 (📤 입력, 📥 결과) */
    h2 {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        margin-top: 1.5rem !important;
        margin-bottom: 1rem !important;
        color: #e5e7eb !important;
        text-align: left !important;
    }
    
    /* 결과 이미지 제목 (정면(0도), 스타일링 컷 1 등) */
    h3 {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        margin-bottom: 1rem !important;
        color: #d1d5db !important;
        text-align: center !important;
    }
    
    /* 페이지 설명 텍스트 */
    .stMarkdown p {
        font-size: 0.95rem !important;
        color: #d1d5db !important;
        line-height: 1.6 !important;
    }
    
    /* 입력 라벨 스타일 */
    .stTextInput label, .stSelectbox label, .stFileUploader label,
    .stSlider label, .stTextArea label, .stCheckbox label {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        color: #e5e7eb !important;
        margin-bottom: 0.5rem !important;
    }
    
    /* Primary 버튼 스타일 */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e88e5 0%, #00acc1 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        padding: 0.75rem 1.5rem !important;
        border: none !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(30, 136, 229, 0.3) !important;
        transition: all 0.3s ease !important;
        height: auto !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1976d2 0%, #0097a7 100%) !important;
        box-shadow: 0 6px 16px rgba(30, 136, 229, 0.4) !important;
        transform: translateY(-2px) !important;
    }
    
    .stButton > button[kind="primary"]:active {
        transform: translateY(0px) !important;
        box-shadow: 0 2px 8px rgba(30, 136, 229, 0.3) !important;
    }
    
    /* 일반 버튼 스타일 (◀ ▶ 네비게이션) */
    .stButton > button:not([kind="primary"]) {
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        padding: 0.5rem !important;
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
        background: white !important;
        color: #475569 !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:not([kind="primary"]):hover {
        background: #f8fafc !important;
        border-color: #cbd5e1 !important;
        transform: scale(1.05) !important;
    }
    
    /* 다운로드 버튼 스타일 */
    .stDownloadButton > button {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        padding: 0.6rem 1.2rem !important;
        border-radius: 6px !important;
        background: #10b981 !important;
        color: white !important;
        border: none !important;
        transition: all 0.2s ease !important;
    }
    
    .stDownloadButton > button:hover {
        background: #059669 !important;
        transform: translateY(-1px) !important;
    }
    
    /* 업로드된 파일 정보 텍스트 */
    .uploadedFileName {
        font-size: 0.85rem !important;
        color: #64748b !important;
    }
    
    /* 체크박스 라벨 및 간격 */
    .stCheckbox {
        margin-bottom: -1rem !important;
    }
    .stCheckbox label p {
        font-size: 0.85rem !important;
        line-height: 1.2 !important;
    }
    
    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, #1e88e5 0%, #00acc1 100%) !important;
    }
    
    /* 구분선 스타일 */
    hr {
        margin: 1.5rem 0 !important;
        border-color: #e2e8f0 !important;
    }
    
    /* 사이드바 스타일 */
    section[data-testid="stSidebar"] {
        width: 330px !important;
        min-width: 330px !important;
    }

    .css-1d391kg {
        padding-top: 2rem !important;
    }
    
    section[data-testid="stSidebar"] h1 {
        font-size: 1.5rem !important;
        color: #ffffff !important;
    }
    
    /* 알림 메시지 스타일 */
    .stAlert {
        font-size: 0.9rem !important;
        padding: 0.75rem 1rem !important;
    }
    
    /* 이미지 캡션 */
    .stImage > div {
        text-align: center !important;
    }
    
    .stImage figcaption {
        font-size: 0.8rem !important;
        color: #64748b !important;
        margin-top: 0.5rem !important;
    }

    /* Custom Progress Bar Styles */
    @keyframes progress-animation {
        0% { background-position: 100% 0; }
        100% { background-position: -100% 0; }
    }
    .progress-container {
        background-color: #4a5568;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        color: #e2e8f0;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .progress-title {
        font-weight: 600;
        font-size: 1rem;
        margin-bottom: 0.8rem;
    }
    .progress-bar-wrapper {
        width: 100%;
        background-color: #2d3748;
        border-radius: 5px;
        overflow: hidden;
    }
    .progress-bar-inner {
        width: 50%;
        height: 20px;
        background: linear-gradient(90deg, #63b3ed, #4299e1, #3182ce);
        background-size: 200% 200%;
        border-radius: 5px;
        animation: progress-animation 2s linear infinite;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 0.8rem;
    }
    .progress-text {
        margin-top: 0.8rem;
        font-size: 0.9rem;
        text-align: center;
        color: #a0aec0;
    }

    /* Metadata Table Styles */
    .metadata-table {
        width: 100%;
        border-collapse: collapse;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin-bottom: 1.5rem;
        background-color: #2d3748;
        color: #e2e8f0;
    }
    .metadata-table th, .metadata-table td {
        padding: 1rem 1.2rem;
        text-align: left;
        border-bottom: 1px solid #4a5568;
    }
    .metadata-table th {
        background-color: #1a202c;
        font-weight: 600;
        width: 150px;
        font-size: 0.95rem;
    }
    .metadata-table td {
        background-color: #2d3748;
        line-height: 1.6;
    }
    .metadata-table ul {
        margin: 0;
        padding-left: 1.2rem;
    }
    .metadata-table li {
        margin-bottom: 0.4rem;
    }

    /* Tooltip Styles */
    .tooltip {
        position: relative;
        display: inline-block;
        cursor: help;
        border-bottom: 1px dotted #4299e1;
        color: #63b3ed;
    }

    .tooltip .tooltiptext {
        visibility: hidden;
        width: 300px;
        background-color: #1a202c;
        color: #e2e8f0;
        text-align: left;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        position: absolute;
        z-index: 1000;
        top: 100%;
        left: 0;
        margin-top: 8px;
        opacity: 0;
        transition: opacity 0.3s, visibility 0.3s;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        border: 1px solid #4a5568;
        font-size: 0.85rem;
        line-height: 1.5;
    }

    .tooltip .tooltiptext::after {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 20px;
        border-width: 6px;
        border-style: solid;
        border-color: transparent transparent #1a202c transparent;
    }

    .tooltip:hover .tooltiptext {
        visibility: visible;
        opacity: 1;
    }
    </style>
    """