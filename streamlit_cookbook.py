import uuid

import streamlit as st
from PIL import Image
from supabase import create_client, Client
import pytesseract 

st.set_page_config(page_title="Recipe Submissions", page_icon="🍽", layout="centered")


@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE"]["URL"]
    key = st.secrets["SUPABASE"]["KEY"]
    return create_client(url, key)


supabase: Client = init_supabase()
BUCKET_NAME = st.secrets["SUPABASE"]["BUCKET"]  # "recipes"

# If needed on your host, set Tesseract path, e.g. on Windows:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def upload_image_to_storage(file) -> str | None:
    """Upload file bytes to Supabase Storage and return the public URL."""
    if file is None:
        return None

    file_bytes = file.read()
    file_ext = file.name.split(".")[-1].lower()
    if file_ext not in ["png", "jpg", "jpeg"]:
        file_ext = "png"

    path = f"recipes/{uuid.uuid4()}.{file_ext}"

    res = supabase.storage.from_(BUCKET_NAME).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": f"image/{file_ext}"},
    )

    if isinstance(res, dict) and res.get("error"):
        st.error(f"Error uploading image: {res['error']['message']}")
        return None

    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(path)
    return public_url


def ocr_image(pil_image: Image.Image) -> str:
    """Run OCR on a PIL image and return extracted text."""
    try:
        text = pytesseract.image_to_string(pil_image)
        return text.strip()
    except Exception as e:
        st.error(f"OCR error: {e}")
        return ""


def save_recipe_to_supabase(
    name: str,
    description: str | None,
    text_body: str | None,
    image_url: str | None,
):
    data = {
        "name": name,
        "description": description,
        "text": text_body,
        "image_url": image_url,
    }

    response = supabase.table("recipes").insert(data).execute()
    if hasattr(response, "error") and response.error:
        raise RuntimeError(response.error)

    return response


def get_recipes_from_supabase():
    response = (
        supabase.table("recipes")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    if hasattr(response, "error") and response.error:
        raise RuntimeError(response.error)

    return response.data or []


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
        name = st.text_input("Recipe name")
        short_desc = st.text_input("Short description (optional)")
        ingredients = st.text_area(
            "Ingredients",
            placeholder="e.g., 2 eggs, 1 cup flour, 1/2 cup milk...",
            height=120,
        )
        instructions = st.text_area(
            "Instructions",
            placeholder="Step-by-step instructions...",
            height=160,
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
                st.success("Text recipe submitted successfully!")
            except Exception as e:
                st.error(f"Error saving recipe: {e}")

# IMAGE SUBMISSION TAB (with OCR)
with tab_image:
    st.subheader("Submit recipe by image")
    st.write(
        "Upload a photo of a handwritten recipe, a recipe screenshot, or a picture of the dish.\n"
        "OCR will try to extract text from the image."
    )

    with st.form("image_recipe_form"):
        name_img = st.text_input("Recipe name (optional)")
        short_desc_img = st.text_input("Short description (optional)")
        uploaded_img = st.file_uploader(
            "Upload recipe or dish image",
            type=["png", "jpg", "jpeg"],
        )
        notes = st.text_area(
            "Optional notes",
            placeholder="Add any notes or context about the recipe.",
            height=120,
        )

        submitted_img = st.form_submit_button("Submit image")

    if submitted_img:
        if uploaded_img is None:
            st.error("Please upload an image to submit.")
        else:
            try:
                # Preview image
                pil_img = Image.open(uploaded_img)
                st.image(pil_img, caption="Uploaded image", use_container_width=True)

                # OCR
                with st.spinner("Running OCR on image..."):
                    ocr_text = ocr_image(pil_img)

                if ocr_text:
                    st.markdown("**Extracted text (OCR):**")
                    st.text_area("OCR text", value=ocr_text, height=200)

                # Combine OCR text and user notes into one text field
                combined_text = ""
                if ocr_text:
                    combined_text += f"OCR text:\n{ocr_text}\n\n"
                if notes:
                    combined_text += f"Notes:\n{notes}"

                # Upload to Supabase (need fresh bytes)
                uploaded_img.seek(0)
                image_url = upload_image_to_storage(uploaded_img)

                if image_url is None:
                    st.error("Could not upload image.")
                else:
                    save_recipe_to_supabase(
                        name=name_img or "Untitled recipe",
                        description=short_desc_img or None,
                        text_body=combined_text or None,
                        image_url=image_url,
                    )
                    st.success("Image recipe (with OCR) submitted successfully!")
            except Exception as e:
                st.error(f"Error saving image recipe: {e}")

# LIST TAB
with tab_list:
    st.subheader("Submitted recipes")

    try:
        recipes = get_recipes_from_supabase()
    except Exception as e:
        st.error(f"Error loading recipes: {e}")
        recipes = []

    if not recipes:
        st.info("No recipes submitted yet. Be the first to share one!")
    else:
        for r in recipes:
            title = r.get("name") or "Untitled recipe"
            with st.expander(title):
                if r.get("description"):
                    st.write(f"_{r['description']}_")

                created_at = r.get("created_at")
                if created_at:
                    st.write(f"Submitted at: {created_at}")

                if r.get("text"):
                    st.markdown("**Details / Notes / OCR text:**")
                    st.text(r["text"])

                if r.get("image_url"):
                    st.markdown("**Image:**")
                    st.markdown(f"[Open image in new tab]({r['image_url']})")
                    st.image(r["image_url"], use_container_width=True)
