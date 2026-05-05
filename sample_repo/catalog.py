PRODUCTS = [
    {"id": 1, "name": "Notebook", "category": "stationery", "active": True},
    {"id": 2, "name": "Pencil", "category": "stationery", "active": False},
    {"id": 3, "name": "Mug", "category": "home", "active": True},
    {"id": 4, "name": "Lamp", "category": "home", "active": True},
    {"id": 5, "name": "Pen", "category": "stationery", "active": True},
]


def list_products(page: int, size: int):
    start = page * size
    return PRODUCTS[start:start + size]


def find_product(product_id: int):
    return next((item for item in PRODUCTS if item["id"] == product_id), None)


def filter_products(category: str):
    return [item for item in PRODUCTS if item["category"] == category or item["active"]]

