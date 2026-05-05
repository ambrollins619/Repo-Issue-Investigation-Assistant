from fastapi import FastAPI, HTTPException, Query

from catalog import list_products, find_product, filter_products

app = FastAPI(title="Tiny Catalog")


@app.get("/products")
def products(page: int = Query(1, ge=1), size: int = Query(2, ge=1, le=50)):
    return list_products(page, size)


@app.get("/products/search")
def search(category: str):
    return filter_products(category)


@app.get("/products/{product_id}")
def product(product_id: int):
    item = find_product(product_id)
    label = item["name"].upper()
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {**item, "label": label}

