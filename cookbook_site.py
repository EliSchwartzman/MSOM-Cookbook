import uuid
from datetime import datetime

import streamlit as st
from PIL import Image
from supabase import create_client, Client
import pytesseract 
import os # Import os for environment check (optional but good practice)

# --- Configuration and Setup ---

st.set_page_config(page_title="Recipe Submissions", page_icon="🍽", layout="centered")

@st.cache_resource 
def init_supabase() -> Client:
    """Initializes and returns the Supabase client using Streamlit secrets."""
    if "SUPABASE" not in st.secrets:
        st.error("FATAL ERROR: Missing SUPABASE configuration in .streamlit/secrets.toml. Please check your file.")
        st.stop()
        
    url = st.secrets["SUPABASE"].get("URL")
    key = st.secrets["SUPABASE"].get("KEY")
    
    if not url or not key:
        st.error("FATAL ERROR: Supabase URL or Key is missing or incomplete in secrets.")
        st.stop()
        
    try:
        # Attempt to create the client
        return create_client(url, key)
    except Exception as e:
        st.error(f"FATAL ERROR: Failed to create Supabase client. Check network connection or credentials. Details: {e}")
        st.stop()

# Initialize Supabase client globally
supabase: Client = init_supabase()
BUCKET_NAME = st.secrets["SUPABASE"].get("BUCKET", "recipes") 

# --- Tesseract/OCR Setup ---

# *** FOOL-PROOF FIX: REMOVED EXPLICIT PATH ***
# Since 'tesseract --version' works, we rely on the system PATH. 
# This avoids the error caused by a path mismatch in the Python script.

# Optional: Check if tesseract is available before running the app logic
try:
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except pytesseract.TesseractNotFoundError:
    st.warning("OCR feature disabled: Tesseract is not installed or not in PATH. Image text extraction will fail.")
    TESSERACT_AVAILABLE = False


# --- Supabase Storage Functions ---

def upload_image_to_storage(file) -> str | None:
    """Upload file bytes to Supabase Storage and return the public URL."""
    if file is None:
        return None

    # Rewind file pointer after previous reads (PIL/OCR)
    file.seek(0) 
    file_bytes = file.read()
    
    file_ext = file.name.split(".")[-1].lower()
    if file_ext not in ["png", "jpg", "jpeg"]:
        file_ext = "jpg" 

    path = f"recipes/{uuid.uuid4()}.{file_ext}"

    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": f"image/{file_ext}"},
        )
        
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(path)
        return public_url
    
    except Exception as e:
        # Added specific advice for storage error
        st.error(f"Error uploading image to Supabase Storage. Check Bucket Name/Policies. Details: {e}")
        return None


# --- OCR Function ---

def ocr_image(pil_image: Image.Image) -> str:
    """Run OCR on a PIL image and return extracted text."""
    if not TESSERACT_AVAILABLE:
        return "OCR failed: Tesseract not found on the system."
        
    try:
        text = pytesseract.image_to_string(pil_image)
        return text.strip()
    except Exception as e:
        st.error(f"OCR execution error: {e}")
        return ""


# --- Supabase DB Functions ---

def save_recipe_to_supabase(
    name: str,
    description: str | None,
    text_body: str | None,
    image_url: str | None,
):
    """Inserts recipe data into the Supabase 'recipes' table."""
    data = {
        "name": name,
        "description": description,
        "text": text_body,
        "image_url": image_url,
    }

    response = supabase.table("recipes").insert(data).execute()
    
    if response and hasattr(response, "error") and response.error:
        # Provide more context for DB errors
        raise RuntimeError(f"Supabase DB Insert Error: {response.error}")
        
    return response


def get_recipes_from_supabase():
    """Fetches all recipes from the Supabase 'recipes' table."""
    response = (
        supabase.table("recipes")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    if response and hasattr(response, "error") and response.error:
        # Provide more context for DB errors
        raise RuntimeError(f"Supabase DB Select Error: {response.error}")

    return response.data or []


# --- Streamlit UI ---

st.title("🍽 Community Recipe Submissions")
st.write(
    "Share your favorite recipes by typing them in or uploading a photo of the recipe or dish."
)

tab_text, tab_image, tab_list = st.tabs(
    ["Text submission", "Image submission", "All recipes"]
)

# TEXT SUBMISSION TAB
with tab_text:
    st.subheader("Submit recipe by text")

    with st.form("text_recipe_form"):
        name = st.text_input("Recipe name", key="text_name")
        short_desc = st.text_input("Short description (optional)", key="text_desc")
        ingredients = st.text_area(
            "Ingredients",
            placeholder="e.g., 2 eggs, 1 cup flour, 1/2 cup milk...",
            height=120,
            key="text_ingredients"
        )
        instructions = st.text_area(
            "Instructions",
            placeholder="Step-by-step instructions...",
            height=160,
            key="text_instructions"
        )

        submitted = st.form_submit_button("Submit recipe")

    if submitted:
        if not name or (not ingredients and not instructions):
            st.error(
                "Please provide at least a name and some ingredients or instructions."
            )
        else:
            full_text = f"Ingredients:\n{ingredients}\n\nInstructions:\n{instructions}"
            try:
                save_recipe_to_supabase(
                    name=name,
                    description=short_desc or None,
                    text_body=full_text,
                    image_url=None,
                )
                st.success("Text recipe submitted successfully! Check the 'All recipes' tab.")
            except Exception as e:
                st.error(f"Error saving recipe: {e}")

# IMAGE SUBMISSION TAB (with editable OCR)
with tab_image:
    st.subheader("Submit recipe by image")
    if not TESSERACT_AVAILABLE:
        st.warning("OCR is unavailable. You will need to manually enter the recipe details.")
    else:
        st.write(
            "OCR will try to extract text from the image for easy editing."
        )

    with st.form("image_recipe_form"):
        name_img = st.text_input("Recipe name (optional)", key="img_name")
        short_desc_img = st.text_input("Short description (optional)", key="img_desc")
        uploaded_img = st.file_uploader(
            "Upload recipe or dish image",
            type=["png", "jpg", "jpeg"],
            key="img_upload"
        )
        notes = st.text_area(
            "Optional notes/context",
            placeholder="Add any notes or context about the recipe.",
            height=120,
            key="img_notes"
        )

        submitted_img = st.form_submit_button("Submit image")

    # The logic runs only after submission
    if submitted_img:
        if uploaded_img is None:
            st.error("Please upload an image to submit.")
            st.stop()
            
        try:
            # 1. Preview image
            pil_img = Image.open(uploaded_img)
            st.image(pil_img, caption="Uploaded image", use_container_width=True)

            # 2. OCR and make it editable
            ocr_text = ""
            if TESSERACT_AVAILABLE:
                with st.spinner("Running OCR on image..."):
                    ocr_text = ocr_image(pil_img)

            # Editable Text Area for Review
            st.markdown("### 📝 Review and Edit Extracted Text")
            if not ocr_text:
                st.warning("OCR could not extract text. Please enter the recipe details manually below.")
                initial_text = ""
            else:
                initial_text = ocr_text

            # Note: Key is changed to prevent Streamlit widget identity conflicts across reruns
            edited_text = st.text_area(
                "OCR/Recipe Text (Editable)", 
                value=initial_text, 
                height=250, 
                key=f"edited_ocr_final_{uuid.uuid4()}" # Dynamic key for robustness
            )
            
            # 3. Combine edited text and user notes for final save
            combined_text = ""
            if edited_text:
                combined_text += f"Recipe Details/OCR Text:\n{edited_text}\n\n"
            if notes:
                combined_text += f"User Notes:\n{notes}"

            # 4. Upload image to Supabase Storage
            image_url = upload_image_to_storage(uploaded_img)

            if image_url is None:
                st.error("Image upload failed. Check Supabase Storage configuration/policies.")
            else:
                # 5. Save metadata to Supabase DB
                save_recipe_to_supabase(
                    name=name_img or "Untitled recipe",
                    description=short_desc_img or None,
                    text_body=combined_text or None,
                    image_url=image_url,
                )
                st.success("Image recipe (with OCR and notes) submitted successfully! Check the 'All recipes' tab.")
        except Exception as e:
            st.error(f"Fatal error saving image recipe: {e}")

# LIST TAB
with tab_list:
    st.subheader("Submitted recipes")

    # Use a placeholder container to show spinner while loading
    recipe_container = st.container()
    
    with st.spinner("Loading recipes..."):
        try:
            recipes = get_recipes_from_supabase()
        except Exception as e:
            st.error(f"Error loading recipes: {e}")
            recipes = []

    with recipe_container:
        if not recipes:
            st.info("No recipes submitted yet. Be the first to share one!")
        else:
            for r in recipes:
                title = r.get("name") or "Untitled recipe"
                with st.expander(title):
                    if r.get("description"):
                        st.write(f"_{r['description']}_")

                    created_at_raw = r.get("created_at")
                    if created_at_raw:
                        try:
                            dt_object = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00')) # Handle Z timezone
                            formatted_date = dt_object.strftime("%B %d, %Y at %I:%M %p")
                            st.caption(f"Submitted on: {formatted_date}")
                        except ValueError:
                            st.caption(f"Submitted at: {created_at_raw}")

                    if r.get("text"):
                        st.markdown("**Details / Notes / OCR text:**")
                        st.markdown(r["text"]) 

                    if r.get("image_url"):
                        st.markdown("**Image:**")
                        st.markdown(f"[Open image in new tab]({r['image_url']})")
                        st.image(r["image_url"], use_container_width=True)