import streamlit as st
import pandas as pd
from github import Github
import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# GitHub configuration
REPO_NAME = "pxlhierarchy/lbstyle"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")

# Pricing (CAD)
PRICE_PER_LB = {"1": 7.50, "2": 5.50, "3": 4.00, "Bundle": 3.75}
COST_PER_LB = 1.79  # Goodwill bins cost
G_PER_LB = 453.592

# Initialize session state
if "inventory" not in st.session_state:
    try:
        logger.debug("Loading inventory.csv...")
        df = pd.read_csv("inventory.csv") if pd.io.common.file_exists("inventory.csv") else pd.DataFrame(columns=[
            "SKU", "Weight_g", "Weight_lb", "Description", "Tier", "Size", "Tags",
            "Measurements", "Pic_Paths", "Price_CAD", "Cost_CAD", "Date_Added", "Sold"
        ])
        st.session_state.inventory = df
        logger.debug("Inventory loaded successfully")
    except Exception as e:
        logger.error(f"Error loading inventory.csv: {e}")
        st.error(f"Failed to load inventory: {e}")
        st.session_state.inventory = pd.DataFrame(columns=[
            "SKU", "Weight_g", "Weight_lb", "Description", "Tier", "Size", "Tags",
            "Measurements", "Pic_Paths", "Price_CAD", "Cost_CAD", "Date_Added", "Sold"
        ])

# Function to save to GitHub
def save_to_github(df):
    try:
        logger.debug(f"Connecting to GitHub with token ending: {GITHUB_TOKEN[-4:]}")
        g = Github(GITHUB_TOKEN)
        logger.debug(f"Accessing repo: {REPO_NAME}")
        repo = g.get_repo(REPO_NAME)
        logger.debug("Verifying branch: main")
        repo.get_branch("main")  # Confirm branch exists
        logger.debug("Checking for existing inventory.csv")
        try:
            contents = repo.get_contents("inventory.csv", ref="main")
            sha = contents.sha
            logger.debug(f"Found inventory.csv, SHA: {sha}")
        except Exception as e:
            logger.debug(f"No inventory.csv or error: {e}")
            sha = None
        csv_content = df.to_csv(index=False, encoding='utf-8')
        logger.debug(f"Prepared CSV content, length: {len(csv_content)} bytes")
        commit_message = f"Update inventory.csv {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        logger.debug(f"Committing: {commit_message}")
        if sha:
            repo.update_file("inventory.csv", commit_message, csv_content, sha, branch="main")
            logger.debug("Updated existing inventory.csv")
        else:
            repo.create_file("inventory.csv", commit_message, csv_content, branch="main")
            logger.debug("Created new inventory.csv")
        logger.info("Successfully saved to inventory.csv on GitHub")
        return True
    except Exception as e:
        logger.error(f"GitHub commit failed: {str(e)}")
        st.error(f"Failed to save to GitHub: {str(e)}")
        return False

# Streamlit UI
st.title("BinRipper.fit Inventory Manager")
option = st.sidebar.selectbox("Select Action", ["Add Item", "View Inventory", "Export Shopify CSV"])

if option == "Add Item":
    with st.form("add_item_form"):
        sku = st.text_input("SKU")
        weight_g = st.number_input("Weight (grams)", min_value=0.0, step=0.1)
        description = st.text_input("Description")
        tier = st.selectbox("Tier", ["1", "2", "3", "Bundle"])
        size = st.selectbox("Size", ["XS", "S", "M", "L", "XL"])
        tags = st.text_input("Tags (comma-separated)")
        measurements = st.text_input("Measurements")
        pic_paths = st.text_input("Picture Paths (comma-separated)")
        submitted = st.form_submit_button("Add Item")
        
        if submitted and sku and weight_g and description:
            logger.debug(f"Adding item: SKU={sku}, Weight_g={weight_g}")
            weight_lb = weight_g / G_PER_LB
            price_cad = round(weight_lb * PRICE_PER_LB[tier], 2)
            cost_cad = round(weight_lb * COST_PER_LB, 2)
            cleaned_tags = ",".join(tag.strip() for tag in tags.split(",") if tag.strip())
            new_item = {
                "SKU": sku,
                "Weight_g": weight_g,
                "Weight_lb": round(weight_lb, 2),
                "Description": description,
                "Tier": tier,
                "Size": size,
                "Tags": f"tier{tier},{cleaned_tags}",
                "Measurements": measurements,
                "Pic_Paths": pic_paths,
                "Price_CAD": price_cad,
                "Cost_CAD": cost_cad,
                "Date_Added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Sold": False
            }
            st.session_state.inventory = pd.concat([st.session_state.inventory, pd.DataFrame([new_item])], ignore_index=True)
            logger.debug("Item added to session state")
            if save_to_github(st.session_state.inventory):
                st.success("Item added and saved to GitHub!")
                st.write(f"SKU={sku}, Weight={weight_g}g ({round(weight_lb, 2)}lb), Tier={tier}, Price=${price_cad} CAD, Cost=${cost_cad} CAD")
            else:
                st.error("Item added locally but failed to save to GitHub.")

elif option == "View Inventory":
    st.write("Current Inventory:")
    st.dataframe(st.session_state.inventory)
    st.write(f"Total Retail Value: ${st.session_state.inventory['Price_CAD'].sum():.2f} CAD")
    st.write(f"Total Cost: ${st.session_state.inventory['Cost_CAD'].sum():.2f} CAD")

elif option == "Export Shopify CSV":
    shopify_df = st.session_state.inventory.copy()
    shopify_df["Handle"] = shopify_df["SKU"]
    shopify_df["Title"] = shopify_df["Description"]
    shopify_df["Body (HTML)"] = shopify_df.apply(
        lambda row: f"<p>Tier {row['Tier']}. Size: {row['Size']}. Measurements: {row['Measurements']}. All sales final.</p>", axis=1)
    shopify_df["Variant SKU"] = shopify_df["SKU"]
    shopify_df["Variant Grams"] = shopify_df["Weight_g"]
    shopify_df["Variant Price"] = shopify_df["Price_CAD"]
    shopify_df["Cost per item"] = shopify_df["Cost_CAD"]
    shopify_df["Status"] = "draft"
    shopify_df["Tags"] = shopify_df["Tags"]
    shopify_df["Option1 Name"] = "Title"
    shopify_df["Option1 Value"] = "Default Title"
    shopify_columns = [
        "Handle", "Title", "Body (HTML)", "Variant SKU", "Variant Grams",
        "Variant Price", "Cost per item", "Tags", "Status", "Option1 Name", "Option1 Value"
    ]
    csv = shopify_df[shopify_columns].to_csv(index=False, encoding='utf-8')
    st.download_button("Download Shopify CSV", csv, "shopify_import.csv", "text/csv")