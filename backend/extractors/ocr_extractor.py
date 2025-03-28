import pytesseract
from PIL import Image
import pdfplumber
import numpy as np
import cv2
import io


pytesseract.pytesseract.tesseract_cmd = r"C:\Users\Me\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

def preprocess_image(image):
    """Applies preprocessing techniques for better OCR accuracy."""
    # Convert PIL image to OpenCV format
    image = np.array(image)

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # Apply adaptive thresholding
    processed_image = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    return Image.fromarray(processed_image)  # Convert back to PIL format

def extract_text_from_scanned_pdf(file):
    """Extracts text from an uploaded scanned PDF file using OCR."""
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Convert page to image
            image = page.to_image(resolution=300).original  
            
            # Apply preprocessing
            processed_image = preprocess_image(image)

            # Perform OCR
            text += pytesseract.image_to_string(processed_image, lang="eng")
    return text
