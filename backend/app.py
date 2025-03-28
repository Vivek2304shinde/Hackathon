
from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify, session
from extractors.pdf_extractor import extract_text_from_pdf, extract_tables_from_pdf, save_tables_to_excel
from extractors.ocr_extractor import extract_text_from_scanned_pdf
from models.ner_model import load_ner_model, extract_entities
from utils.feedback_handler import FeedbackHandler
from flask_cors import CORS  # For cross-origin requests
from dotenv import load_dotenv
import os
import io
import traceback
from datetime import datetime
from werkzeug.utils import secure_filename
import numpy as np
from flask_session import Session



# Load environment variables
load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins for API testing


app.config['SESSION_TYPE'] = 'filesystem'  # Store sessions on the server
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_DIR'] = os.path.join(app.instance_path, 'sessions')
Session(app)

# Ensure necessary folders exist
if not os.path.exists(app.config['SESSION_FILE_DIR']):
    os.makedirs(app.config['SESSION_FILE_DIR'])

    
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-key-please-change')

# Initialize feedback handler
feedback_handler = FeedbackHandler()

# Allowed file types
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_floats(obj):
    """Recursively converts numpy.float32 to Python float to avoid JSON serialization errors."""
    if isinstance(obj, np.float32):
        return float(obj)
    if isinstance(obj, list):
        return [convert_floats(x) for x in obj]
    if isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    return obj

# Load NER model once at startup
print("✅ Loading NER model...")
ner_model = load_ner_model()
print("✅ NER model loaded successfully!")

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "Unsupported file type"}), 400

        # Create timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save the uploaded file
        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0]
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_{timestamp}.pdf")
        file.save(file_path)

        # Extract text
        print("🛠️ Extracting text from file...")
        try:
            text = extract_text_from_scanned_pdf(io.BytesIO(file.read())) if file_path.lower().endswith(('jpg', 'png')) else extract_text_from_pdf(file_path)
            print("✅ Text extraction complete!")
        except Exception as e:
            print("🔥 OCR or text extraction failed!", traceback.format_exc())
            return jsonify({"error": f"Failed to extract text: {str(e)}"}), 500

        # Extract entities
        print("🛠️ Extracting named entities...")
        try:
            entities, confidence_scores = extract_entities(text, ner_model)
            print("✅ Entity extraction complete!")
        except Exception as e:
            print("🔥 NER extraction failed!", traceback.format_exc())
            return jsonify({"error": f"Failed to extract entities: {str(e)}"}), 500

        # Extract tables and save to Excel
        print("🛠️ Extracting tables from PDF...")
        try:
            tables = extract_tables_from_pdf(file_path)
            excel_filename = f"{base_name}_{timestamp}_output.xlsx"
            excel_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_filename)
            save_tables_to_excel(tables, excel_path)

            # Store filename and path in session
            session['excel_filename'] = excel_filename  # Only filename
            session['excel_path'] = excel_path  # Full path (if needed for debugging)

            print(f"✅ Table extraction and Excel generation complete! Excel Path: {excel_path}")
        except Exception as e:
            print("🔥 Table extraction failed!", traceback.format_exc())
            tables = None

        # Debug session to ensure data is set correctly
        print(f"Session Data After Upload: {session}")

        excel_filename = secure_filename(f"{base_name}_{timestamp}_output.xlsx")  # Secure the Excel filename too
        excel_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_filename)


        # Response
        response_data = {
            "message": "File processed successfully!",
            "text": text,
            "entities": entities,
            "excel_filename": excel_filename if tables else None,  # Return the filename for download use
            "confidence_scores": confidence_scores,
            "tables_extracted": bool(tables)
        }
        return jsonify(response_data), 200

    except Exception as e:
        print("🔥 Internal Server Error!", traceback.format_exc())
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500




@app.route('/download_excel', methods=['GET'])
def download_excel():
    """Route to download the generated Excel file"""

    try:
        # Retrieve the Excel filename from the query parameters
        excel_filename = request.args.get('filename')  # Expecting filename in query params

        # Log session and request details for debugging
        print("Retrieving session data...")
        print(f"Session Data: {dict(session)}")
        print(f"Requested Excel Filename: {excel_filename}")

        # Validate the filename
        if not excel_filename:
            print("Excel filename not provided in request.")
            return jsonify({"error": "Excel filename is required"}), 400

        # Sanitize the filename
        from werkzeug.utils import secure_filename
        excel_filename = secure_filename(excel_filename)

        # Construct the full file path
        excel_filepath = os.path.join(app.config['UPLOAD_FOLDER'], excel_filename)

        # Check if the file exists
        if not os.path.exists(excel_filepath):
            print(f"File does not exist at path: {excel_filepath}")
            return jsonify({"error": f"File not found: {excel_filename}"}), 404

        # Serve the file for download
        return send_file(
            excel_filepath,
            as_attachment=True,
            download_name=excel_filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        return jsonify({"error": f"Error downloading file: {str(e)}"}), 500



if __name__ == '__main__':
    # Create uploads directory if it doesn't exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    print("✅ PDF-Doc project backend is running on port 5000")
    app.run(debug=True, port=5000)