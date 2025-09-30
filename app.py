import streamlit as st
import pandas as pd
from github import Github
import datetime
import logging

# Configure logging to file and console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# GitHub configuration
# EDIT HERE: Update REPO_NAME if your GitHub repo changes (format: "username/repo")
REPO_NAME = "pxlhierarchy/lbstyle"
# EDIT HERE: GITHUB_TOKEN is stored in .streamlit/secrets.toml; update there, not here
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")

# Pricing configuration (all in CAD)
# EDIT HERE: Adjust PRICE_PER_LB for each tier (e.g., {"1": 8.00} for Tier 1 at $8.00/lb)
PRICE_PER_LB = {
    "1": 7.50,  # Tier 1 price per pound
    "2": 5.50,  # Tier 2 price per pound
    "3": 4.00,  # Tier 3 price per pound
    "Bundle": 3.75  # Bundle price per pound
}
# EDIT HERE: Update COST_PER_LB for Goodwill bins cost (e.g., 2.00 for $2.00/lb)
COST_PER_LB = 1.79  # Goodwill bins cost per pound
# EDIT HERE: Update G_PER_LB if grams-to-pounds conversion changes
G_PER_LB = 453.592  # Grams per pound for weight conversion

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

# Function to save to GitHub and local
def save_to_github(df):
    try:
        logger.debug(f"Connecting to GitHub with token ending: {GITHUB_TOKEN[-4:]}")
        g = Github(GITHUB_TOKEN)
        logger.debug(f"Accessing repo: {REPO_NAME}")
        repo = g.get_repo(REPO_NAME)
        # EDIT HERE: Change branch to "master" if your repo uses master instead of main
        branch = "main"
        logger.debug(f"Verifying branch: {branch}")
        repo.get_branch(branch)
        logger.debug("Checking for existing inventory.csv")
        file_path = "inventory.csv"
        try:
            contents = repo.get_contents(file_path, ref=branch)
            sha = contents.sha
            logger.debug(f"Found {file_path}, SHA: {sha}")
        except Exception as e:
            logger.debug(f"No {file_path} or error: {e}")
            sha = None
        csv_content = df.to_csv(index=False, encoding='utf-8')
        logger.debug(f"Prepared CSV content, length: {len(csv_content)} bytes")
        commit_message = f"Update inventory.csv {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        logger.debug(f"Committing: {commit_message}")
        if sha:
            repo.update_file(file_path, commit_message, csv_content, sha, branch=branch)
            logger.debug(f"Updated {file_path}")
        else:
            repo.create_file(file_path, commit_message, csv_content, branch=branch)
            logger.debug(f"Created {file_path}")
        # Save to local inventory.csv
        try:
            df.to_csv("inventory.csv", index=False, encoding='utf-8')
            logger.debug("Saved to local inventory.csv")
        except Exception as e:
            logger.error(f"Failed to save local inventory.csv: {e}")
            st.error(f"Failed to save local inventory.csv: {e}")
        logger.info("Successfully saved to inventory.csv on GitHub and local")
        return True
    except Exception as e:
        logger.error(f"GitHub commit failed: {str(e)}")
        st.error(f"Failed to save to GitHub: {str(e)}")
        return False

# Streamlit UI
st.title("BinRipper.fit Inventory Manager")
# EDIT HERE: Add or modify actions in the sidebar (e.g., ["Add Item", "View Inventory", "New Action"])
option = st.sidebar.selectbox("Select Action", ["Add Item", "View Inventory", "Export Shopify CSV"])

if option == "Add Item":
    with st.form("add_item_form"):
        sku = st.text_input("SKU")
        weight_g = st.number_input("Weight (grams)", min_value=0.0, step=0.1)
        description = st.text_input("Description")
        # EDIT HERE: Modify tier options if needed (e.g., add "4" for a new tier)
        tier = st.selectbox("Tier", ["1", "2", "3", "Bundle"])
        size = st.text_input("Size (e.g., XS, 23x24)")
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
                "Size tributaries": [
                    "Size", size,
                    "Tags", f"tier{tier},{cleaned_tags}",
                    "Measurements", measurements,
                    "Pic_Paths", pic_paths,
                    "Price_CAD", price_cad,
                    "Cost_CAD", cost_cad,
                    "Date_Added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Sold": False
            }
            st.session_state.inventory = pd.concat([st.session_state.inventory, pd.DataFrame([new_item])], ignore_index=True)
            logger.debug("Item added to session state")
            if save_to_github(st.session_state.inventory):
                st.success("Item added and saved to GitHub and local!")
                st.write(f"SKU={sku}, Weight={weight_g}g ({round(weight_lb, 2)}lb), Tier={tier}, Price=${price_cad} CAD, Cost=${cost_cad} CAD")
            else:
                st.error("Item added locally but failed to save to GitHub.")

elif option == "View Inventory":
    st.write("Current Inventory:")
    st.dataframe(st.session_state.inventory)
    st.write(f"Total Retail Value: ${st.session_state.inventory['Price_CAD'].sum():.2f} CAD")
    st.write(f"Total Cost: ${st.session_state.inventory['Cost_CAD'].sum():.2f} CAD")

elif option == "Export Shopify CSV":
    st.write("Select items to export to Shopify CSV:")
    # Filter options
    with st.form("export_filter_form"):
        # EDIT HERE: Add more filter options (e.g., by Tier, Tags) if needed
        export_all = st.checkbox("Export all items", value=True)
        selected_skus = st.multiselect("Select SKUs (optional)", options=st.session_state.inventory["SKU"].tolist())
        date_filter = st.date_input("Export items added on or after (optional)", value=None)
        unsold_only = st.checkbox("Export only unsold items", value=False)
        submitted = st.form_submit_button("Generate CSV")
    
    if submitted:
        shopify_df = st.session_state.inventory.copy()
        if not export_all:
            # Apply filters
            if selected_skus:
                shopify_df = shopify_df[shopify_df["SKU"].isin(selected_skus)]
            if date_filter:
                shopify_df = shopify_df[pd.to_datetime(shopify_df["Date_Added"]).dt.date >= date_filter]
            if unsold_only:
                shopify_df = shopify_df[shopify_df["Sold"] == False]
        if shopify_df.empty:
            st.error("No items match the selected filters.")
        else:
            shopify_df["Handle"] = shopify_df["SKU"]
            shopify_df["Title"] = shopify_df["Description"]
            shopify_df["Body (HTML)"] = shopify_df.apply(
                lambda row: f"<p>Tier {row['Tier']}. Size: {row['Size']}. Measurements: {row['Measurements']}.</p>", axis=1)
            shopify_df["Variant SKU"] = shopify_df["SKU"]
            shopify_df["Variant Grams"] = shopify_df["Weight_g"]
            shopify_df["Variant Price"] = shopify_df["Price_CAD"]
            shopify_df["Cost per item"] = shopify_df["Cost_CAD"]
            shopify_df["Status"] = "draft"
            shopify_df["Tags"] = shopify_df["Tags"]
            shopify_df["Option1 Name"] = "Title"
            shopify_df["Option1 Value"] = "Default Title"
            # EDIT HERE: Modify shopify_columns to add/remove fields for Shopify CSV export
            shopify_columns = [
                "Handle", "Title", "Body (HTML)", "Variant SKU", "Variant Grams",
                "Variant Price", "Cost per item", "Tags", "Status", "Option1 Name", "Option1 Value"
            ]
            csv = shopify_df[shopify_columns].to_csv(index=False, encoding='utf-8')
            st.download_button("Download Shopify CSV", csv, "shopify_import.csv", "text/csv")
            st.write(f"Exported {len(shopify_df)} items to CSV.")