import os
import re
import tempfile
import streamlit as st
from PyPDF2 import PdfReader, PdfWriter
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import zipfile

# Set page config
st.set_page_config(page_title="FCR Extractor", page_icon="📄", layout="wide")

# ============= Configuration =============
# These paths should be configured based on your deployment environment
POPPLER_PATH = r"C:\poppler\Library\bin"  # Update this for your server
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ============= Environment Setup =============
os.environ['PATH'] = f"{POPPLER_PATH};{os.environ['PATH']}"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def extract_text_from_page(page, temp_dir):
    """Extract text from a single PDF page using best available method"""
    try:
        # First try direct extraction
        text = page.extract_text()
        if text and text.strip():
            return text
        
        # Fallback to OCR
        temp_pdf_path = os.path.join(temp_dir, "temp_page.pdf")
        with open(temp_pdf_path, "wb") as f:
            writer = PdfWriter()
            writer.add_page(page)
            writer.write(f)
        
        images = convert_from_path(
            temp_pdf_path,
            poppler_path=POPPLER_PATH,
            dpi=300,
            fmt='jpeg'
        )
        
        if images:
            return pytesseract.image_to_string(images[0], lang='eng+ara')
        
        return ""
    
    except Exception as e:
        st.error(f"Error extracting text: {str(e)}")
        return ""

def find_fcr_ranges(pdf_path, temp_dir):
    """Identify ranges of pages that belong to each FCR"""
    fcr_ranges = {}  # {fcr_number: (start_page, end_page)}
    current_fcr = None
    start_page = 0
    
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        total_pages = len(reader.pages)
        
        for page_num in range(total_pages):
            page = reader.pages[page_num]
            text = extract_text_from_page(page, temp_dir)
            
            if not text:
                continue
                
            # Search for FCR numbers in this page
            patterns = [
                r'RECEIPT\s*NO[.:]?\s*([A-Z0-9]+[\(\d+\)]?)',
                r'FCR\s*NO[.:]?\s*([A-Z0-9]+)',
                r'رقم\s*الإيصال[\s:]*([A-Z0-9]+)'
            ]
            
            found_fcr = None
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    found_fcr = matches[0]
                    break
            
            # If we found a new FCR, finalize the previous range
            if found_fcr and found_fcr != current_fcr:
                if current_fcr is not None:
                    fcr_ranges[current_fcr] = (start_page, page_num - 1)
                current_fcr = found_fcr
                start_page = page_num
            
            # Special case for last page
            if page_num == total_pages - 1 and current_fcr is not None:
                fcr_ranges[current_fcr] = (start_page, page_num)
    
    return fcr_ranges

def split_pdf_by_fcr_ranges(pdf_path, fcr_ranges, output_dir):
    """Split the PDF into separate files based on FCR ranges"""
    output_files = []
    
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        
        for fcr_num, (start, end) in fcr_ranges.items():
            # Clean the FCR number for filename
            clean_fcr_num = re.sub(r'[^\w\-_\. ]', '_', str(fcr_num))
            output_path = os.path.join(output_dir, f"FCR_{clean_fcr_num}.pdf")
            
            writer = PdfWriter()
            # Add all pages in this range
            for page_num in range(start, end + 1):
                writer.add_page(reader.pages[page_num])
            
            # Save as PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            output_files.append((f"FCR_{clean_fcr_num}.pdf", output_path))
    
    return output_files

def create_zip(output_files, zip_path):
    """Create a zip file containing all extracted FCRs"""
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for filename, filepath in output_files:
            zipf.write(filepath, arcname=filename)
    return zip_path

def main():
    st.title("FCR Receipt Extractor")
    st.markdown("Upload a PDF containing multiple FCR receipts to split them into individual files.")
    
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_file is not None:
        with st.spinner("Processing PDF..."):
            # Create a temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Save uploaded file to temp location
                input_pdf_path = os.path.join(temp_dir, "input.pdf")
                with open(input_pdf_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Find FCR ranges
                fcr_ranges = find_fcr_ranges(input_pdf_path, temp_dir)
                
                if not fcr_ranges:
                    st.error("No FCR numbers found in the document")
                    return
                
                # Split PDF
                output_files = split_pdf_by_fcr_ranges(input_pdf_path, fcr_ranges, temp_dir)
                
                # Create zip file
                zip_path = os.path.join(temp_dir, "extracted_fcrs.zip")
                create_zip(output_files, zip_path)
                
                # Display results
                st.success(f"Found {len(fcr_ranges)} FCR receipts in the document")
                
                # Show FCR ranges found
                with st.expander("Show FCR page ranges"):
                    for fcr_num, (start, end) in fcr_ranges.items():
                        st.write(f"- {fcr_num}: Pages {start+1}-{end+1}")
                
                # Download buttons
                st.subheader("Download Extracted FCRs")
                
                # Option to download all as zip
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="Download All as ZIP",
                        data=f,
                        file_name="extracted_fcrs.zip",
                        mime="application/zip"
                    )
                
                # Individual download buttons
                st.write("Or download individual FCRs:")
                cols = st.columns(3)  # 3 columns for buttons
                
                for idx, (filename, filepath) in enumerate(output_files):
                    with open(filepath, "rb") as f:
                        with cols[idx % 3]:
                            st.download_button(
                                label=filename,
                                data=f,
                                file_name=filename,
                                mime="application/pdf"
                            )

if __name__ == "__main__":
    # Check for required libraries
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as e:
        st.error(f"Required libraries not installed: {str(e)}")
        st.stop()
    
    main()