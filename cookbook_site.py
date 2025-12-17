import uuid
from datetime import datetime

import streamlit as st
from PIL import Image
from supabase import create_client, Client
# Removed: import pytesseract 

st.set_page_config(page_title="Recipe Submissions", page_icon="🍽", layout="centered")

# --- Configuration and Setup ---

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
        return create_client(url, key)
    except Exception as e:
        st.error(f"FATAL ERROR: Failed to create Supabase client. Check network connection or credentials. Details: {e}")
        st.stop()

# Initialize Supabase client globally
supabase: Client = init_supabase()
BUCKET_NAME = st.secrets["SUPABASE"].get("BUCKET", "recipes") 

# Removed: pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# Removed: ocr_image function

# --- Supabase Storage Functions ---

def upload_image_to_storage(file) -> str | None:
    """Upload file bytes to Supabase Storage and return the public URL."""
    if file is None:
        return None

    # Rewind file pointer after previous reads (PIL)
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
        st.error(f"Error uploading image to Supabase Storage. Check Bucket Name/Policies. Details: {e}")
        return None


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

# IMAGE SUBMISSION TAB (Simplified without OCR)
with tab_image:
    st.subheader("Submit recipe by image")
    st.write(
        "Upload a photo of the dish or recipe card. You must manually enter the recipe details."
    )

    with st.form("image_recipe_form"):
        name_img = st.text_input("Recipe name", key="img_name_required") # Made name required by flow
        short_desc_img = st.text_input("Short description (optional)", key="img_desc")
        uploaded_img = st.file_uploader(
            "Upload recipe or dish image",
            type=["png", "jpg", "jpeg"],
            key="img_upload"
        )
        # Re-purposed the notes field for the main recipe text
        recipe_details = st.text_area(
            "Recipe Details / Ingredients & Instructions",
            placeholder="Enter ingredients, instructions, or notes here...",
            height=250,
            key="img_recipe_details"
        )

        submitted_img = st.form_submit_button("Submit image")

    if submitted_img:
        if uploaded_img is None or not name_img:
            st.error("Please provide a name and upload an image to submit.")
            st.stop()
            
        try:
            # 1. Preview image
            pil_img = Image.open(uploaded_img)
            st.image(pil_img, caption="Uploaded image", use_container_width=True)
            
            # 2. Upload image to Supabase Storage
            image_url = upload_image_to_storage(uploaded_img)

            if image_url is None:
                st.error("Image upload failed. Check Supabase Storage configuration/policies.")
            else:
                # 3. Save metadata to Supabase DB
                save_recipe_to_supabase(
                    name=name_img,
                    description=short_desc_img or None,
                    text_body=recipe_details or None,
                    image_url=image_url,
                )
                st.success("Image recipe submitted successfully! Check the 'All recipes' tab.")
        except Exception as e:
            st.error(f"Fatal error saving image recipe: {e}")

# LIST TAB
with tab_list:
    st.subheader("Submitted recipes")

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
                            # Handle Z timezone
                            dt_object = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00')) 
                            formatted_date = dt_object.strftime("%B %d, %Y at %I:%M %p")
                            st.caption(f"Submitted on: {formatted_date}")
                        except ValueError:
                            st.caption(f"Submitted at: {created_at_raw}")

                    if r.get("text"):
                        st.markdown("**Details / Notes / Recipe Text:**")
                        st.markdown(r["text"]) 

                    if r.get("image_url"):
                        st.markdown("**Image:**")
                        st.markdown(f"[Open image in new tab]({r['image_url']})")
                        st.image(r["image_url"], use_container_width=True)