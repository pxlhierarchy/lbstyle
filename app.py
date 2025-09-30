import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import os
from github import Github
import base64

# Initialize GitHub client for persistence
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = "pxlhierarchy/lbstyle"  # Replace with your GitHub repo (e.g., "johndoe/thrift-app")
CSV_PATH = "inventory.csv"

@st.cache_data
def load_inventory():
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH)
            # Ensure all expected columns exist
            expected_columns = ['SKU', 'Weight_g', 'Weight_lb', 'Description', 'Tier', 'Size', 'Tags', 
                               'Measurements', 'Pic_Paths', 'Price_CAD', 'Cost_CAD', 'Date_Added', 'Sold']
            for col in expected_columns:
                if col not in df.columns:
                    df[col] = None if col != 'Sold' else False
            return df
        except Exception as e:
            st.error(f"Error loading inventory.csv: {e}")
            return pd.DataFrame(columns=expected_columns)
    return pd.DataFrame(columns=expected_columns)

def save_inventory(df):
    df.to_csv(CSV_PATH, index=False)
    # Commit to GitHub
    if GITHUB_TOKEN:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(REPO_NAME)
            with open(CSV_PATH, "rb") as file:
                content = file.read()
            encoded_content = base64.b64encode(content).decode()
            try:
                # Update existing file
                file = repo.get_contents(CSV_PATH)
                repo.update_file(CSV_PATH, "Update inventory.csv", encoded_content, file.sha)
            except:
                # Create new file if it doesn't exist
                repo.create_file(CSV_PATH, "Create inventory.csv", encoded_content)
        except Exception as e:
            st.error(f"Error committing to GitHub: {e}")

# Initialize session state for df
if 'df' not in st.session_state:
    st.session_state.df = load_inventory()

def save_df(df):
    st.session_state.df = df
    save_inventory(df)

def add_item(df, sku, weight_g, description, tier, size='', tags='', measurements='', pic_paths=''):
    weight_lb = weight_g / 453.592  # Convert grams to pounds
    # Calculate price based on tier (non-subscriber rates, CAD)
    price_per_lb = {'1': 7.50, '2': 5.50, '3': 4.00, 'Bundle': 3.75}
    price = round(weight_lb * price_per_lb[str(tier)], 2) if str(tier) in price_per_lb else 0.00
    # Calculate cost at $1.79/lb CAD
    cost = round(weight_lb * 1.79, 2)
    date_added = datetime.now().strftime('%Y-%m-%d')
    # Clean tags: remove spaces after commas
    tags = ','.join(tag.strip() for tag in tags.split(',') if tag.strip()) if tags else ''
    new_row = pd.DataFrame([{
        'SKU': sku, 'Weight_g': weight_g, 'Weight_lb': weight_lb, 'Description': description, 'Tier': tier,
        'Size': size, 'Tags': tags, 'Measurements': measurements, 'Pic_Paths': pic_paths,
        'Price_CAD': price, 'Cost_CAD': cost, 'Date_Added': date_added, 'Sold': False
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    # Debug price and cost calculation
    st.write(f"Debug: SKU={sku}, Weight={weight_g}g ({weight_lb:.2f}lb), Tier={tier}, Price=${price} CAD, Cost=${cost} CAD")
    return df

def mark_sold(df, sku):
    df.loc[df['SKU'] == sku, 'Sold'] = True
    return df

def get_slow_movers(df, days=60):
    df['Date_Added'] = pd.to_datetime(df['Date_Added'], errors='coerce')
    cutoff = datetime.now() - timedelta(days=days)
    slow_movers = df[(df['Sold'] == False) & (df['Date_Added'] <= cutoff)].copy()
    slow_movers['Action'] = slow_movers['Tier'].apply(lambda t: 'Drop price to $2-3/lb non-sub or bundle with Tier 2/1' if t == 3 else 'Bundle with Tier 3 items')
    return slow_movers[['SKU', 'Description', 'Tier', 'Size', 'Tags', 'Weight_g', 'Weight_lb', 'Price_CAD', 'Cost_CAD', 'Action']]

def create_bundle(df, bundle_sku, item_skus, bundle_description):
    item_skus = [s.strip() for s in item_skus.split(',')]
    bundle_items = df[df['SKU'].isin(item_skus) & (df['Sold'] == False)]
    if len(bundle_items) != len(item_skus):
        st.error("Some items not found or already sold.")
        return df
    total_weight_g = bundle_items['Weight_g'].sum()
    total_weight_lb = total_weight_g / 453.592
    # Calculate bundle price at $3.75/lb and cost at $1.79/lb
    price = round(total_weight_lb * 3.75, 2)
    cost = round(total_weight_lb * 1.79, 2)
    # Combine tags from items, add 'Bundle'
    bundle_tags = ','.join(set(','.join(bundle_items['Tags'].dropna()).split(',') + ['Bundle']))
    new_row = pd.DataFrame([{
        'SKU': bundle_sku, 'Weight_g': total_weight_g, 'Weight_lb': total_weight_lb, 'Description': bundle_description,
        'Tier': 'Bundle', 'Size': '', 'Tags': bundle_tags, 'Measurements': '',
        'Pic_Paths': ','.join(bundle_items['Pic_Paths'].str.cat(sep=',').split(',')), 
        'Price_CAD': price, 'Cost_CAD': cost, 'Date_Added': datetime.now().strftime('%Y-%m-%d'), 'Sold': False
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.loc[df['SKU'].isin(item_skus), 'Sold'] = True
    return df

def export_shopify_csv(df):
    shopify_rows = []
    for _, row in df.iterrows():
        if row['Sold']: continue
        tags = f"tier{row['Tier']}" if row['Tier'] != 'Bundle' else 'Bundle'
        if row['Tags']:  # Append custom tags, no spaces
            tags += f",{row['Tags']}"
        main_row = {
            'Handle': row['SKU'],
            'Title': row['Description'],
            'Body (HTML)': f"<p>Tier {row['Tier']}. Size: {row['Size'] or 'N/A'}. Measurements: {row['Measurements'] or 'N/A'}. All sales final.</p>",
            'Vendor': 'Your Thrift Arbitrage',
            'Product Category': 'Apparel & Accessories > Clothing',
            'Tags': tags,
            'Published': 'false',
            'Option1 Name': 'Title',
            'Option1 Value': 'Default Title',
            'Variant SKU': row['SKU'],
            'Variant Grams': round(row['Weight_g']) if pd.notna(row['Weight_g']) else '',
            'Variant Inventory Tracker': 'shopify',
            'Variant Inventory Qty': 1,
            'Variant Inventory Policy': 'deny',
            'Variant Fulfillment Service': 'manual',
            'Variant Price': row['Price_CAD'],
            'Cost per item': row['Cost_CAD'],
            'Variant Requires Shipping': 'true',
            'Variant Taxable': 'true',
            'Status': 'draft'
        }
        shopify_rows.append(main_row)
    shopify_df = pd.DataFrame(shopify_rows)
    csv_buffer = io.StringIO()
    shopify_df.to_csv(csv_buffer, index=False)
    return csv_buffer.getvalue()

st.title("Thrift Inventory Manager")

# Sidebar for actions
st.sidebar.title("Actions")
action = st.sidebar.selectbox("Choose action:", ["View Inventory", "Add Item", "Mark Sold", "Slow Movers Report", "Create Bundle", "Export Shopify CSV"])

if action == "View Inventory":
    st.subheader("Current Inventory")
    # Display all fields with wider columns
    st.dataframe(st.session_state.df, use_container_width=True)
    # Calculate and display totals for unsold items
    unsold_df = st.session_state.df[st.session_state.df['Sold'] == False]
    total_retail = unsold_df['Price_CAD'].sum() if not unsold_df.empty else 0.00
    total_cost = unsold_df['Cost_CAD'].sum() if not unsold_df.empty else 0.00
    st.write(f"**Total Retail Value (Unsold):** ${total_retail:.2f} CAD")
    st.write(f"**Total Cost (Unsold):** ${total_cost:.2f} CAD")

elif action == "Add Item":
    st.subheader("Add New Item")
    with st.form("add_item"):
        sku = st.text_input("SKU")
        weight_g = st.number_input("Weight (grams)", min_value=10.0, step=1.0)
        desc = st.text_area("Description")
        tier = st.selectbox("Tier", [1, 2, 3])
        size = st.text_input("Size (optional, e.g., M or 32x34)")
        tags = st.text_input("Tags (optional, comma-separated, e.g., tshirt,casual)")
        # Always show measurements input, but only use for Tier 3
        meas = st.text_input("Measurements (optional, required for Tier 3)")
        pics = st.text_input("Pic Paths (local paths for reference)")
        submitted = st.form_submit_button("Add Item")
        if submitted and sku:
            # Only pass measurements for Tier 3
            measurements = meas if tier == 3 else ''
            st.session_state.df = add_item(st.session_state.df, sku, weight_g, desc, tier, size, tags, measurements, pics)
            save_df(st.session_state.df)
            st.success(f"Item added! {weight_g}g ({weight_g/453.592:.2f}lb, ${st.session_state.df.iloc[-1]['Price_CAD']} CAD, Cost ${st.session_state.df.iloc[-1]['Cost_CAD']} CAD)")

elif action == "Mark Sold":
    st.subheader("Mark Item Sold")
    sku = st.text_input("Enter SKU to mark sold")
    if st.button("Mark Sold") and sku:
        st.session_state.df = mark_sold(st.session_state.df, sku)
        save_df(st.session_state.df)
        st.success("Marked as sold!")

elif action == "Slow Movers Report":
    st.subheader("Slow Movers (60+ Days Unsold)")
    slow_df = get_slow_movers(st.session_state.df)
    st.dataframe(slow_df, use_container_width=True)
    csv = slow_df.to_csv(index=False)
    st.download_button("Download Report CSV", csv, "slow_movers.csv", "text/csv")

elif action == "Create Bundle":
    st.subheader("Create Bundle")
    with st.form("create_bundle"):
        bundle_sku = st.text_input("Bundle SKU")
        item_skus = st.text_input("Item SKUs (comma-separated)")
        bundle_desc = st.text_area("Bundle Description")
        submitted = st.form_submit_button("Create Bundle")
        if submitted and bundle_sku and item_skus:
            st.session_state.df = create_bundle(st.session_state.df, bundle_sku, item_skus, bundle_desc)
            save_df(st.session_state.df)
            st.success("Bundle created!")

elif action == "Export Shopify CSV":
    st.subheader("Shopify Export (Drafts)")
    csv_data = export_shopify_csv(st.session_state.df)
    st.download_button("Download Shopify CSV", csv_data, "shopify_import.csv", "text/csv")