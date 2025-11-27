# app.py
import streamlit as st
import json
import PIL.Image
import io
from datetime import datetime
from gemini.extract import extract_metadata, extract_monthly, extract_totals
from gemini.clean import clean_gemini_json, clean_totals_json
from gemini.plot import generate_plot
# from streamlit_image_comparison import image_comparison

# --- Page config ---
st.set_page_config(
    page_title="Rainfall Dashboard 🌧️",
    page_icon="🌦️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS polished look ---
st.markdown(
    """
    <style>
    /* small top padding */
    .css-1d391kg {padding-top: 1rem;}
    h1 { text-align: left; color: #0b5cff; font-weight:700 }
    .stButton>button { border-radius: 8px; padding: 8px 14px; }
    .metric { background: rgba(11,92,255,0.06); border-radius: 8px; padding: 8px }
    .card { padding: 16px; border-radius: 12px; box-shadow: 0 8px 24px rgba(20,20,50,0.06); background: #fff }
    .center { display:flex; justify-content:center; align-items:center; }
    .small-muted { font-size:12px; color: #666; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Header ---
st.title("Rainfall Table Extractor")
st.markdown("Upload a 10-year monthly rainfall *table image* — the app will extract, clean, visualize, and let you download results.")

# --- Sidebar: controls & image slider ---
with st.sidebar:
    st.header("Upload & Options")
    uploaded = st.file_uploader("Upload an image (png/jpg/jpeg)", type=["png", "jpg", "jpeg"])

    st.markdown("---")
    st.subheader("Processing Options")
    model_choice = st.selectbox("OCR Model", ["Gemini 2.5-Flash-Preview-09-2025"], index=0)
    validate_image = st.checkbox("Validate image size/quality", value=True)

    st.markdown("---")
    st.subheader("Example Images")

    # Example images (raw strings OK on Windows)
    example_images = [
        r"C:\Users\Michelle\scratch\everydata\images\ABERDARE-MARDY_ABERDARE-MARDY_page5.png",
        r"C:\Users\Michelle\scratch\everydata\images\ABERDARE-NANTHIR-RES_ABERDARE-NANTHIR-RES_page9.png",
        r"C:\Users\Michelle\scratch\everydata\images\ABERDARE-NANTHIR-RES_ABERDARE-NANTHIR-RES_page7.png"
    ]

    # init index if missing
    if "idx" not in st.session_state:
        st.session_state.idx = 0

    # show selected example preview
    try:
        st.image(example_images[st.session_state.idx], use_container_width=True)
    except Exception:
        st.info("Example image not found locally. Upload your own image to preview.")

    # buttons below the image
    col_l, col_c, col_r = st.columns([1, 1, 1])
    with col_l:
        if st.button("◀"):
            st.session_state.idx = (st.session_state.idx - 1) % len(example_images)
    with col_c:
        st.write("")  # spacer to keep buttons under image
    with col_r:
        if st.button("▶"):
            st.session_state.idx = (st.session_state.idx + 1) % len(example_images)

    st.markdown("---")
    st.caption("Tips: Use a clear photo, ensure months & totals visible.")
    st.caption("When you upload a new file, previous results will be cleared.")

# --- Helper utilities ---
@st.cache_data(ttl=3600)
def load_image(file) -> PIL.Image.Image:
    file.seek(0)
    img = PIL.Image.open(file).convert("RGB")
    return img

def validate(img: PIL.Image.Image):
    msgs = []
    if img.width < 600:
        msgs.append("Gambar lebar < 600px: ekstraksi kemungkinan tidak akurat.")
    if img.height < 400:
        msgs.append("Gambar tinggi < 400px: ekstraksi kemungkinan tidak akurat.")
    return msgs

def make_downloadable_json(obj) -> bytes:
    # return raw bytes for st.download_button
    return json.dumps(obj, indent=2).encode("utf-8")

# --- Ensure session state keys ---
if "ready" not in st.session_state:
    st.session_state.ready = False
if "uploaded_name" not in st.session_state:
    st.session_state.uploaded_name = None

# If a new upload occurs, reset previous results
if uploaded:
    # compare name & size to decide if new
    uploaded_identifier = f"{uploaded.name}-{uploaded.size}"
    if st.session_state.uploaded_name != uploaded_identifier:
        # new file uploaded -> clear previous
        st.session_state.uploaded_name = uploaded_identifier
        st.session_state.ready = False
        for k in ("metadata", "monthly", "totals", "buf"):
            if k in st.session_state:
                del st.session_state[k]

# Add space before the right column
st.markdown("<br>", unsafe_allow_html=True)

# --- Main layout ---
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("Preview")
    if uploaded:
        img = load_image(uploaded)
        st.image(img, width=400)

        if validate_image:
            msgs = validate(img)
            if msgs:
                for m in msgs:
                    st.warning(m)
            else:
                st.success("Gambar memenuhi ukuran minimal.")

        process_btn = st.button("Process Image", type="primary")
    else:
        st.info("Silakan upload gambar di sidebar untuk memulai.")
        process_btn = False

# Add space before the right column
st.markdown("<br><br>", unsafe_allow_html=True)

with col_right:
    st.subheader("Results")

    # Processing block - saves outputs to session_state
    if process_btn and uploaded:
        progress_text = st.empty()
        progress_bar = st.progress(0)

        try:
            # 1) Extract
            progress_text.info("1/4 — Extracting metadata...")
            progress_bar.progress(10)
            metadata_raw = extract_metadata(img)  # returns JSON string or similar

            progress_text.info("2/4 — Extracting monthly table...")
            progress_bar.progress(30)
            monthly_raw = extract_monthly(img)

            progress_text.info("3/4 — Extracting totals...")
            progress_bar.progress(50)
            totals_raw = extract_totals(img)

            # 2) Clean
            progress_text.info("4/4 — Cleaning extracted data...")
            progress_bar.progress(70)
            metadata = json.loads(metadata_raw)
            monthly = clean_gemini_json(json.loads(monthly_raw))
            totals = clean_totals_json(json.loads(totals_raw), monthly)

            progress_bar.progress(85)

            # Plot generation (matplotlib fig)
            fig = generate_plot(img, metadata, monthly, totals)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
            buf.seek(0)

            # store into session_state so results persist after rerun
            st.session_state.metadata = metadata
            st.session_state.monthly = monthly
            st.session_state.totals = totals
            st.session_state.buf = buf  # BytesIO
            st.session_state.ready = True

            progress_bar.progress(100)
            progress_text.success("Selesai")

        except Exception as e:
            st.exception(e)
            progress_text.error("Terjadi kesalahan saat memproses gambar.")
            progress_bar.empty()

    # === Persistent results view (tabs) ===
    if st.session_state.get("ready"):
        tab_plot, tab_json, tab_downloads = st.tabs(["Plot", "JSON", "Downloads"])

        # ---- Plot tab ----
        with tab_plot:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("Rainfall Plot")
            # st.image accepts BytesIO or raw bytes
            try:
                st.image(st.session_state.buf, use_container_width=True)
            except Exception:
                # fallback
                st.image(st.session_state.buf.getvalue(), use_container_width=True)


        # ---- JSON tab ----
        with tab_json:
            with st.expander("Extracted Metadata JSON", expanded=False):
                st.json(st.session_state.metadata)

            with st.expander("Extracted Monthly Data JSON", expanded=False):
                st.json(st.session_state.monthly)

            with st.expander("Extracted Totals JSON", expanded=False):
                st.json(st.session_state.totals)

        # ---- Downloads tab ----
        with tab_downloads:
            st.markdown("Download your outputs below.")
            c1, c2, c3 = st.columns([1,1,1])
            # Use raw bytes for downloads (so button works reliably)
            json_monthly_bytes = make_downloadable_json(st.session_state.monthly)
            json_totals_bytes = make_downloadable_json(st.session_state.totals)
            # image bytes
            img_bytes = st.session_state.buf.getvalue()

            with c1:
                st.download_button(
                    "Download Monthly JSON",
                    data=json_monthly_bytes,
                    file_name="monthly.json",
                    mime="application/json",
                    use_container_width=True
                )
            with c2:
                st.download_button(
                    "Download Totals JSON",
                    data=json_totals_bytes,
                    file_name="totals.json",
                    mime="application/json",
                    use_container_width=True
                )
            with c3:
                st.download_button(
                    "Download Plot (PNG)",
                    data=img_bytes,
                    file_name="rainfall_plot.png",
                    mime="image/png",
                    use_container_width=True
                )

    elif uploaded and not st.session_state.get("ready"):
        st.info("Tekan 'Process Image' setelah mengonfirmasi preview untuk mengekstrak data.")

# Footer
st.markdown("---")
st.caption(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
