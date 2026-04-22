"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateCustomerEmail = updateCustomerEmail;
const Customer_1 = require("../entity/Customer");
/**
 * Scenario 2 — Update a customer's email atomically.
 * The update is wrapped in a transaction so it either fully applies
 * or rolls back on any error, leaving no inconsistent state.
 */
async function updateCustomerEmail(dataSource, customerId, newEmail) {
    return dataSource.transaction(async (manager) => {
        const customer = await manager.findOne(Customer_1.Customer, { where: { customerId } });
        if (!customer)
            throw new Error(`Customer ${customerId} not found`);
        const oldEmail = customer.email;
        customer.email = newEmail;
        await manager.save(customer);
        console.log(`[Scenario 2] Customer #${customerId} email: ${oldEmail} → ${newEmail}`);
        return customer;
    });
}
