import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  OneToMany,
  JoinColumn,
  CreateDateColumn,
} from "typeorm";
import { Customer } from "./Customer";
import { OrderItem } from "./OrderItem";

@Entity("orders")
export class Order {
  @PrimaryGeneratedColumn()
  orderId!: number;

  @Column()
  customerId!: number;

  @CreateDateColumn()
  orderDate!: Date;

  @Column("decimal", { precision: 10, scale: 2, default: 0 })
  totalAmount!: number;

  @ManyToOne(() => Customer, (customer) => customer.orders)
  @JoinColumn({ name: "customerId" })
  customer!: Customer;

  @OneToMany(() => OrderItem, (item) => item.order)
  orderItems!: OrderItem[];
}
