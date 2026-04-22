"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
require("reflect-metadata");
const typeorm_1 = require("typeorm");
const Customer_1 = require("./entity/Customer");
const Product_1 = require("./entity/Product");
const Order_1 = require("./entity/Order");
const OrderItem_1 = require("./entity/OrderItem");
const placeOrder_1 = require("./scenarios/placeOrder");
const updateEmail_1 = require("./scenarios/updateEmail");
const addProduct_1 = require("./scenarios/addProduct");
const AppDataSource = new typeorm_1.DataSource({
    type: "postgres",
    host: process.env.DB_HOST ?? "db",
    port: Number(process.env.DB_PORT ?? 5432),
    username: process.env.DB_USER ?? "user",
    password: process.env.DB_PASSWORD ?? "password",
    database: process.env.DB_NAME ?? "online_store",
    entities: [Customer_1.Customer, Product_1.Product, Order_1.Order, OrderItem_1.OrderItem],
    synchronize: true,
    logging: false,
});
async function waitForDb(retries = 10, delayMs = 3000) {
    for (let i = 1; i <= retries; i++) {
        try {
            await AppDataSource.initialize();
            console.log("Connected to database");
            return;
        }
        catch {
            console.log(`DB not ready (attempt ${i}/${retries}), retrying in ${delayMs / 1000}s…`);
            await new Promise((r) => setTimeout(r, delayMs));
        }
    }
    throw new Error("Could not connect to the database");
}
async function seed() {
    const customerRepo = AppDataSource.getRepository(Customer_1.Customer);
    const productRepo = AppDataSource.getRepository(Product_1.Product);
    if ((await customerRepo.count()) === 0) {
        await customerRepo.save(customerRepo.create({ firstName: "Alice", lastName: "Smith", email: "alice@example.com" }));
    }
    if ((await productRepo.count()) === 0) {
        await productRepo.save([
            productRepo.create({ productName: "Laptop", price: 999.99 }),
            productRepo.create({ productName: "Mouse", price: 29.99 }),
            productRepo.create({ productName: "USB Hub", price: 49.99 }),
        ]);
    }
    console.log("Seed data ready");
}
async function main() {
    await waitForDb();
    await seed();
    const customerRepo = AppDataSource.getRepository(Customer_1.Customer);
    const productRepo = AppDataSource.getRepository(Product_1.Product);
    const customer = await customerRepo.findOneOrFail({ where: {} });
    const laptop = await productRepo.findOneOrFail({ where: { productName: "Laptop" } });
    const mouse = await productRepo.findOneOrFail({ where: { productName: "Mouse" } });
    // Scenario 1: place an order
    await (0, placeOrder_1.placeOrder)(AppDataSource, customer.customerId, [
        { productId: laptop.productId, quantity: 1 },
        { productId: mouse.productId, quantity: 2 },
    ]);
    // Scenario 2: update customer email
    await (0, updateEmail_1.updateCustomerEmail)(AppDataSource, customer.customerId, "alice.new@example.com");
    // Scenario 3: add a new product
    await (0, addProduct_1.addProduct)(AppDataSource, "Mechanical Keyboard", 149.99);
    console.log("\nAll scenarios completed successfully");
    await AppDataSource.destroy();
}
main().catch((err) => {
    console.error(err);
    process.exit(1);
});
