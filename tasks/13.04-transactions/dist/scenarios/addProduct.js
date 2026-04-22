"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.addProduct = addProduct;
const Product_1 = require("../entity/Product");
/**
 * Scenario 3 — Add a new product atomically.
 * If any error occurs during insertion the transaction rolls back,
 * leaving the products table in a consistent state.
 */
async function addProduct(dataSource, productName, price) {
    return dataSource.transaction(async (manager) => {
        const product = manager.create(Product_1.Product, { productName, price });
        await manager.save(product);
        console.log(`[Scenario 3] Product added — id: ${product.productId}, name: "${product.productName}", price: ${Number(product.price).toFixed(2)}`);
        return product;
    });
}
