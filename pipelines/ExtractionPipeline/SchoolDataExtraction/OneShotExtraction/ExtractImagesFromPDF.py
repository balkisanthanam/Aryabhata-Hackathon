import fitz  # PyMuPDF
import os

def extract_figures_from_pdf(pdf_path, output_dir="extracted_figures"):
    """
    Extracts all embedded images from a PDF and saves them to a directory.

    :param pdf_path: Path to the PDF file.
    :param output_dir: Directory to save the extracted images.
    """
    # Create the output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Open the PDF file
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF {pdf_path}: {e}")
        return

    print(f"Processing {pdf_path}...")
    file_prefix = os.path.splitext(os.path.basename(pdf_path))[0]
    images_found = 0

    # 1. Iterate through each page
    for page_index in range(17,19): #range(len(doc)):
        page = doc.load_page(page_index)
        
        # 2. Get a list of all images on the page
        # get_images(full=True) gives more detailed info
        image_list = page.get_images(full=True)

        if image_list:
            print(f"Found {len(image_list)} images on page {page_index + 1}")
            images_found += len(image_list)

        # 3. Iterate through the images on the page
        for image_index, img in enumerate(image_list):
            # img[0] is the 'xref' -- the internal ID of the image
            xref = img[0]

            # 4. Extract the raw image data
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                # 5. Create a file name
                image_filename = f"{file_prefix}-page-{page_index + 1}-img-{image_index}.{image_ext}"
                image_path = os.path.join(output_dir, image_filename)

                # 6. Save the image to the output directory
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
            
            except Exception as e:
                print(f"Error extracting image {xref} on page {page_index + 1}: {e}")

    doc.close()
    if images_found == 0:
        print("No embedded images found in this PDF.")
    else:
        print(f"Finished. Extracted {images_found} images to {output_dir}")


# --- How to use the function ---

# List of PDFs you want to process
pdf_files = [
    r'ExtractionPipeline\input\Paper_20200509203411.pdf',
    # "another_paper.pdf",
    # "a_third_paper.pdf"
]

output_folder = r"ExtractionPipeline\output\JEEMain"

for pdf in pdf_files:
    extract_figures_from_pdf(pdf, output_folder)
