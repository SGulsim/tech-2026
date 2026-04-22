"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.placeOrder = placeOrder;
const Order_1 = require("../entity/Order");
const OrderItem_1 = require("../entity/OrderItem");
const Product_1 = require("../entity/Product");
/**
 * Scenario 1 — Place an order.
 * 1. Create an Order record.
 * 2. For each item, fetch the product price and create an OrderItem.
 * 3. Update Order.totalAmount = sum of all subtotals.
 * Everything runs in a single atomic transaction.
 */
async function placeOrder(dataSource, customerId, items) {
    return dataSource.transaction(async (manager) => {
        // Step 1: create order
        const order = manager.create(Order_1.Order, { customerId, totalAmount: 0 });
        await manager.save(order);
        // Step 2: create order items
        let total = 0;
        for (const item of items) {
            const product = await manager.findOne(Product_1.Product, {
                where: { productId: item.productId },
            });
            if (!product)
                throw new Error(`Product ${item.productId} not found`);
            const subtotal = Number(product.price) * item.quantity;
            total += subtotal;
            const orderItem = manager.create(OrderItem_1.OrderItem, {
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
