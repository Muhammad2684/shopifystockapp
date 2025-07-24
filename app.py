import os
import requests
from flask import Flask, render_template, abort
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Shopify API Configuration ---
STORE_URL = os.getenv("SHOPIFY_STORE_URL")
API_VERSION = os.getenv("SHOPIFY_API_VERSION")
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
METAFIELD_NAMESPACE = os.getenv("METAFIELD_NAMESPACE")
METAFIELD_KEY = os.getenv("METAFIELD_KEY")

# API endpoint for GraphQL
GRAPHQL_URL = f"{STORE_URL}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json",
}

# Mapping of URL slugs to Shopify tags and page titles
CATEGORIES = {
    "simple": {"tag": "HJMQS", "title": "Simple"},
    "2-button": {"tag": "HJMQ2B", "title": "2 Button"},
    "7-button": {"tag": "HJMQ7B", "title": "7 Button"},
    "quilt": {"tag": "HJMQQ", "title": "Quilt"},
}

def run_graphql_query(query):
    """Helper function to run a query against the Shopify GraphQL API."""
    try:
        response = requests.post(GRAPHQL_URL, headers=HEADERS, json={'query': query})
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        # This will print the specific connection error to your console for debugging
        print(f"Error connecting to Shopify API: {e}")
        return None

def process_product_edges(edges):
    """Helper function to process the product data returned from GraphQL."""
    processed_products = []
    if not edges:
        return processed_products

    for edge in edges:
        node = edge['node']
        current_qty = node['variants']['edges'][0]['node']['inventoryQuantity'] if node['variants']['edges'] else 0
        
        threshold = 0
        if node['metafield']:
            threshold = int(node['metafield']['value'])

        product_data = {
            "title": node['title'],
            "image_url": node['featuredImage']['url'] if node['featuredImage'] else None,
            "current_qty": current_qty,
            "threshold": threshold,
        }
        processed_products.append(product_data)
        
    return processed_products

@app.route("/")
def show_urgent():
    """
    Displays the "Urgent" page.
    Shows all products from the four main tags that have negative inventory.
    """
    all_tags = [cat["tag"] for cat in CATEGORIES.values()]
    tag_query_string = " OR ".join([f"tag:'{tag}'" for tag in all_tags])
    
    # NEW, SIMPLIFIED QUERY: Just get all products with any of the tags.
    # We will filter for negative inventory in Python, which is more reliable.
    query = f"""
    {{
      products(first: 250, query: "({tag_query_string})") {{
        edges {{
          node {{
            id
            title
            featuredImage {{
              url
            }}
            variants(first: 1) {{
              edges {{
                node {{
                  inventoryQuantity
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    
    data = run_graphql_query(query)
    
    if data is None or 'errors' in data:
        print("GraphQL Error:", data.get('errors'))
        return render_template('urgent_page.html', products=[], page_title="Urgent")
        
    products_to_display = []
    product_edges = data.get('data', {}).get('products', {}).get('edges', [])

    # Loop through ALL fetched products and check their inventory here
    for edge in product_edges:
        node = edge['node']
        
        # Check if the variants list is not empty before trying to access it
        if node['variants']['edges']:
            current_qty = node['variants']['edges'][0]['node']['inventoryQuantity']
            
            # THE CRITICAL LOGIC: Only add the product if its quantity is negative
            if current_qty < 0:
                product_data = {
                    "title": node['title'],
                    "image_url": node['featuredImage']['url'] if node['featuredImage'] else None,
                    "current_qty": current_qty,
                    "needed_qty": 0 - current_qty # Calculate qty needed to get to 0
                }
                products_to_display.append(product_data)

    sorted_products = sorted(products_to_display, key=lambda p: p['needed_qty'], reverse=True)

    return render_template(
        'urgent_page.html', 
        products=sorted_products, 
        page_title="Urgent"
    )

@app.route("/<category_slug>")
def show_category(category_slug):
    """
    Displays pages for "Simple", "2 Button", "7 Button", and "Quilt".
    Shows products where current stock is below the custom threshold.
    """
    if category_slug not in CATEGORIES:
        abort(404)

    category = CATEGORIES[category_slug]
    tag = category["tag"]
    
    query = f"""
    {{
      products(first: 250, query: "tag:'{tag}'") {{
        edges {{
          node {{
            id
            title
            featuredImage {{ url }}
            variants(first: 1) {{
              edges {{ node {{ inventoryQuantity }} }}
            }}
            metafield(namespace: "{METAFIELD_NAMESPACE}", key: "{METAFIELD_KEY}") {{
              value
            }}
          }}
        }}
      }}
    }}
    """
    
    data = run_graphql_query(query)
    
    # --- START OF FIX ---
    # FIRST, check for a connection error
    if data is None:
        return render_template('category_page.html', products=[], page_title=category["title"])
        
    # SECOND, check for an API error
    if 'errors' in data:
        print("GraphQL API Error:", data.get('errors'))
        return render_template('category_page.html', products=[], page_title=category["title"])
    # --- END OF FIX ---

    product_edges = data.get('data', {}).get('products', {}).get('edges', [])
    all_products = process_product_edges(product_edges)
    
    products_to_display = []
    for product in all_products:
        needed_qty = product['threshold'] - product['current_qty']
        if needed_qty > 0:
            product['needed_qty'] = needed_qty
            products_to_display.append(product)

    sorted_products = sorted(products_to_display, key=lambda p: p['needed_qty'], reverse=True)

    return render_template(
        'category_page.html',
        products=sorted_products,
        page_title=category["title"]
    )

@app.route("/testall")
def test_all_products():
    """
    A simple test route to fetch the first 5 products
    with NO filtering to make sure the connection and data reading works.
    THIS VERSION HAS EXTRA DEBUGGING.
    """
    # --- STEP 1: PRINT A MESSAGE TO THE TERMINAL TO CONFIRM THIS CODE IS RUNNING ---
    print("\n" + "="*50)
    print("--- RUNNING /testall DEBUGGING ROUTE ---")
    print("="*50)

    query = """
    {
      products(first: 5) {
        edges {
          node {
            id
            title
            status
            featuredImage { url }
            variants(first: 1) {
              edges {
                node { inventoryQuantity }
              }
            }
          }
        }
      }
    }
    """
    # --- STEP 2: PRINT THE EXACT QUERY WE ARE SENDING ---
    print("\n[DEBUG] Sending GraphQL Query:\n", query)

    data = run_graphql_query(query)

    # --- STEP 3: THIS IS THE MOST IMPORTANT STEP. PRINT THE RAW RESPONSE ---
    print("\n[DEBUG] RAW RESPONSE FROM SHOPIFY:\n", data)
    print("\n" + "="*50)


    # The rest of the function tries to process the data
    if data is None or 'errors' in data or 'data' not in data:
        print("[RESULT] Test failed or returned no data. Check the RAW RESPONSE above.")
        return render_template('urgent_page.html', products=[], page_title="Test Failed - Check Terminal")

    products_to_display = []
    # Using .get() safely navigates the dictionary structure
    product_edges = data.get('data', {}).get('products', {}).get('edges', [])
    
    print(f"[RESULT] Found {len(product_edges)} product edges in the response.")

    for edge in product_edges:
        node = edge.get('node', {})
        current_qty_node = node.get('variants', {}).get('edges', [{}])[0].get('node', {})
        current_qty = current_qty_node.get('inventoryQuantity', 'N/A')
        
        product_data = {
            "title": f"{node.get('title')} (Status: {node.get('status')})", # Adding status to the title for display
            "image_url": node.get('featuredImage', {}).get('url') if node.get('featuredImage') else None,
            "current_qty": current_qty,
            "needed_qty": "N/A"
        }
        products_to_display.append(product_data)

    return render_template('urgent_page.html', products=products_to_display, page_title="All Products Test")


if __name__ == "__main__":
    app.run(debug=True)