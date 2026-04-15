import { Entity, PrimaryGeneratedColumn, Column, ManyToOne, JoinColumn } from "typeorm";
import { Order } from "./Order";
import { Product } from "./Product";

@Entity("order_items")
export class OrderItem {
  @PrimaryGeneratedColumn()
  orderItemId!: number;

  @Column()
  orderId!: number;

  @Column()
  productId!: number;

  @Column()
  quantity!: number;

  @Column("decimal", { precision: 10, scale: 2 })
  subtotal!: number;

  @ManyToOne(() => Order, (order) => order.orderItems)
  @JoinColumn({ name: "orderId" })
  order!: Order;

  @ManyToOne(() => Product, (product) => product.orderItems)
  @JoinColumn({ name: "productId" })
  product!: Product;
}
