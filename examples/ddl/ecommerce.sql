-- E-commerce DDL for ontology auto-generation testing
-- Contains: high-quality tables, low-quality table, system table, M:N relation table

-- High quality: customer table (has comments, has FK-referenced columns)
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY COMMENT '客户ID',
    customer_name VARCHAR(100) COMMENT '客户姓名',
    customer_type ENUM('individual', 'enterprise') COMMENT '客户类型: 个人/企业',
    phone VARCHAR(20) COMMENT '手机号',
    email VARCHAR(100) COMMENT '邮箱',
    register_time DATETIME COMMENT '注册时间',
    annual_spend DECIMAL(12,2) COMMENT '年消费额'
) COMMENT '客户信息表';

-- High quality: product table
CREATE TABLE product (
    product_id BIGINT PRIMARY KEY COMMENT '商品ID',
    product_name VARCHAR(200) COMMENT '商品名称',
    category_id BIGINT COMMENT '分类ID',
    price DECIMAL(10,2) COMMENT '单价',
    stock INT COMMENT '库存数量',
    description TEXT COMMENT '商品描述'
) COMMENT '商品信息表';

-- High quality: order table (has FK to customer)
CREATE TABLE `order` (
    order_id BIGINT PRIMARY KEY COMMENT '订单ID',
    customer_id BIGINT COMMENT '客户ID',
    order_time DATETIME COMMENT '下单时间',
    total_amount DECIMAL(12,2) COMMENT '订单总金额',
    status ENUM('pending', 'paid', 'shipped', 'completed', 'cancelled') COMMENT '订单状态',
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
) COMMENT '订单表';

-- High quality: order_item table (has FKs to order and product)
CREATE TABLE order_item (
    item_id BIGINT PRIMARY KEY COMMENT '订单项ID',
    order_id BIGINT COMMENT '订单ID',
    product_id BIGINT COMMENT '商品ID',
    quantity INT COMMENT '购买数量',
    unit_price DECIMAL(10,2) COMMENT '成交单价',
    FOREIGN KEY (order_id) REFERENCES `order`(order_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
) COMMENT '订单明细表';

-- Low quality: temp table (no comments, meaningless column names) -- tests DDL completion
CREATE TABLE tmp_2024 (
    c1 INT,
    c2 VARCHAR(50),
    c3 DATE,
    c4 DECIMAL(10,2)
);

-- System table: should NOT produce business relations -- tests FK filter
CREATE TABLE system_log (
    log_id BIGINT PRIMARY KEY,
    user_id BIGINT,
    action VARCHAR(100),
    log_time DATETIME,
    FOREIGN KEY (user_id) REFERENCES customer(customer_id)
) COMMENT '系统操作日志表';

-- M:N relation table: tests reification
CREATE TABLE product_tag (
    product_id BIGINT,
    tag_id BIGINT,
    PRIMARY KEY (product_id, tag_id)
) COMMENT '商品-标签关联表';
