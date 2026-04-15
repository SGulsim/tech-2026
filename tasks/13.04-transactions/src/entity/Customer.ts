import { Entity, PrimaryGeneratedColumn, Column, OneToMany } from "typeorm";
import { Order } from "./Order";

@Entity("customers")
export class Customer {
  @PrimaryGeneratedColumn()
  customerId!: number;

  @Column({ length: 100 })
  firstName!: string;

  @Column({ length: 100 })
  lastName!: string;

  @Column({ unique: true, length: 255 })
  email!: string;

  @OneToMany(() => Order, (order) => order.customer)
  orders!: Order[];
}
