import { DataSource } from "typeorm";
import { Product } from "../entity/Product";

/**
 * Scenario 3 — Add a new product atomically.
 * If any error occurs during insertion the transaction rolls back,
 * leaving the products table in a consistent state.
 */
export async function addProduct(
  dataSource: DataSource,
  productName: string,
  price: number
): Promise<Product> {
  return dataSource.transaction(async (manager) => {
    const product = manager.create(Product, { productName, price });
    await manager.save(product);

    console.log(
      `[Scenario 3] Product added — id: ${product.productId}, name: "${product.productName}", price: ${Number(product.price).toFixed(2)}`
    );
    return product;
  });
}
