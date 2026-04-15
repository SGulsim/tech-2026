import { DataSource } from "typeorm";
import { Order } from "../entity/Order";
import { OrderItem } from "../entity/OrderItem";
import { Product } from "../entity/Product";

interface OrderItemInput {
  productId: number;
  quantity: number;
}

/**
 * Scenario 1 — Place an order.
 * 1. Create an Order record.
 * 2. For each item, fetch the product price and create an OrderItem.
 * 3. Update Order.totalAmount = sum of all subtotals.
 * Everything runs in a single atomic transaction.
 */
export async function placeOrder(
  dataSource: DataSource,
  customerId: number,
  items: OrderItemInput[]
): Promise<Order> {
  return dataSource.transaction(async (manager) => {
    // Step 1: create order
    const order = manager.create(Order, { customerId, totalAmount: 0 });
    await manager.save(order);

    // Step 2: create order items
    let total = 0;
    for (const item of items) {
      const product = await manager.findOne(Product, {
        where: { productId: item.productId },
      });
      if (!product) throw new Error(`Product ${item.productId} not found`);

      const subtotal = Number(product.price) * item.quantity;
      total += subtotal;

      const orderItem = manager.create(OrderItem, {
        orderId: order.orderId,
        productId: item.productId,
        quantity: item.quantity,
        subtotal,
      });
      await manager.save(orderItem);
    }

    // Step 3: update total
    order.totalAmount = total;
    await manager.save(order);

    console.log(`[Scenario 1] Order #${order.orderId} placed. Total: ${total.toFixed(2)}`);
    return order;
  });
}
