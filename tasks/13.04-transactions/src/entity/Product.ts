import { Entity, PrimaryGeneratedColumn, Column, OneToMany } from "typeorm";
import { OrderItem } from "./OrderItem";

@Entity("products")
export class Product {
  @PrimaryGeneratedColumn()
  productId!: number;

  @Column({ length: 255 })
  productName!: string;

  @Column("decimal", { precision: 10, scale: 2 })
  price!: number;

  @OneToMany(() => OrderItem, (item) => item.product)
  orderItems!: OrderItem[];
}
