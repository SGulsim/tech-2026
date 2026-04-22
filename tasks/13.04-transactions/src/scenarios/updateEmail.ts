import { DataSource } from "typeorm";
import { Customer } from "../entity/Customer";

/**
 * Scenario 2 — Update a customer's email atomically.
 * The update is wrapped in a transaction so it either fully applies
 * or rolls back on any error, leaving no inconsistent state.
 */
export async function updateCustomerEmail(
  dataSource: DataSource,
  customerId: number,
  newEmail: string,
): Promise<Customer> {
  return dataSource.transaction(async (manager) => {
    const customer = await manager.findOne(Customer, { where: { customerId } });
    if (!customer) throw new Error(`Customer ${customerId} not found`);

    const oldEmail = customer.email;
    customer.email = newEmail;
    await manager.save(customer);

    console.log(
      `[Scenario 2] Customer #${customerId} email: ${oldEmail} → ${newEmail}`,
    );
    return customer;
  });
}
