import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def task_func(product_dict, product_keys):
    """
    Creates a profit report for a list of products based on a specific product dictionary
    that includes the quantity, price, and profit of each product. Additionally, calculates
    the average price and profit for all considered products, and plots a bar chart
    of the profit for each product.

    Args:
        product_dict (dict): A dictionary where keys are product names and values are
                             dictionaries containing 'quantity', 'price', and 'profit'.
                             Example: {'Laptop': {'quantity': 10, 'price': 1200, 'profit': 200}}
        product_keys (list): A list of product names to consider for the report.

    Returns:
        tuple: A tuple containing:
            DataFrame: A pandas DataFrame with columns
                       ['Product', 'Quantity', 'Price', 'Profit', 'Average Price', 'Average Profit'].
            Axes: A matplotlib Axes object representing the plotted bar chart of profit for each product
                  (None if no products are considered).
    """
    products = []
    quantities = []
    prices = []
    profits = []

    # Filter products based on product_keys and extract relevant data
    for key in product_keys:
        if key in product_dict:
            product_info = product_dict[key]
            products.append(key)
            quantities.append(product_info.get('quantity', 0))
            prices.append(product_info.get('price', 0))
            profits.append(product_info.get('profit', 0))

    # Initialize DataFrame and Axes object
    df = pd.DataFrame(columns=['Product', 'Quantity', 'Price', 'Profit', 'Average Price', 'Average Profit'])
    ax = None

    if not products:
        # If no products are considered, return an empty DataFrame and None for Axes
        return df, ax

    # Calculate average price and profit for the considered products
    avg_price = np.mean(prices)
    avg_profit = np.mean(profits)

    # Create the DataFrame
    df = pd.DataFrame({
        'Product': products,
        'Quantity': quantities,
        'Price': prices,
        'Profit': profits
    })

    # Add average price and average profit columns
    df['Average Price'] = avg_price
    df['Average Profit'] = avg_profit

    # Create the bar chart
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(df['Product'], df['Profit'], color='skyblue')
    ax.set_xlabel('Product')
    ax.set_ylabel('Profit')
    ax.set_title('Profit per Product')
    ax.tick_params(axis='x', rotation=45) # Rotate x-axis labels for better readability
    plt.tight_layout() # Adjust layout to prevent labels from overlapping

    return df, ax