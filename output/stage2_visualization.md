# Stage 2: Concepts

```mermaid
classDiagram
    class concept_da1c28cc {
        <<data>>
        name: 客户
    }
    class concept_d6876145 {
        <<data>>
        name: CustomerType
    }
    class concept_ae58cc26 {
        <<data>>
        name: 商品
    }
    class concept_c584853c {
        <<data>>
        name: 订单
    }
    class concept_738ec83e {
        <<data>>
        name: SystemLog
    }
    class concept_e02ab2fe {
        <<data>>
        name: 商品-标签关联
    }
    class concept_4698f45e {
        <<data>>
        name: Tag
    }
    class concept_20f34e25 {
        <<data>>
        name: 电商系统产品
    }
    class concept_77eb4efe {
        <<data>>
        name: 介绍
    }
    class concept_0b91d985 {
        <<data>>
        name: 企业客户
    }
    class concept_646c0723 {
        <<data>>
        name: VIP客户
    }
    class concept_7ed9f01c {
        <<data>>
        name: 专属客服
    }
    class concept_a3b53bd6 {
        <<data>>
        name: 折扣优惠
    }
    class concept_c0f3f7f1 {
        <<data>>
        name: 手机号
    }
    class concept_ab979b3b {
        <<data>>
        name: 邮箱
    }
    class concept_2b92b2b9 {
        <<data>>
        name: 账户
    }
    class concept_f02414b3 {
        <<logic>>
        name: 物流状态
    }
    class concept_a636504e {
        <<data>>
        name: 电子产品
    }
    class concept_d2a1155a {
        <<data>>
        name: 服装
    }
    class concept_3bec5a51 {
        <<data>>
        name: 食品
    }
    class concept_1f5e2edf {
        <<data>>
        name: 智能手机
    }
    class concept_adc84bc9 {
        <<data>>
        name: iPhone
    }
    class concept_dd2c3ca3 {
        <<data>>
        name: 男装
    }
    class concept_108dcb84 {
        <<data>>
        name: 女装
    }
    class concept_4370ef61 {
        <<data>>
        name: 童装
    }
    class concept_516698dc {
        <<data>>
        name: 配饰
    }
    class concept_9b53fe35 {
        <<logic>>
        name: 购买数量
    }
    class concept_17e483dc {
        <<logic>>
        name: 待支付
    }
    class concept_6ee75059 {
        <<logic>>
        name: 已发货
    }
    class concept_4c674706 {
        <<logic>>
        name: 已完成
    }
    class concept_887233e7 {
        <<logic>>
        name: 已取消
    }
    class concept_9342edf7 {
        <<logic>>
        name: 24小时
    }
    class concept_e8ab9652 {
        <<logic>>
        name: 时效标准
    }
    class concept_f96d4dfc {
        <<logic>>
        name: 运输中
    }
    class concept_15990e0e {
        <<logic>>
        name: 已签收
    }
    class concept_3c4c78e4 {
        <<logic>>
        name: 微信支付
    }
    class concept_8601c002 {
        <<logic>>
        name: 支付宝
    }
    class concept_0058d92e {
        <<logic>>
        name: 银行卡支付
    }
    class concept_455e3f2d {
        <<logic>>
        name: 价格
    }
    class concept_935f8ed2 {
        <<application>>
        name: 专属商品目录
    }
    class concept_07606d9d {
        <<application>>
        name: 历史消费记录
    }
    class concept_48a8348d {
        <<application>>
        name: 已完成的订单记录
    }
    class concept_162804d3 {
        <<logic>>
        name: 11位数字
    }
    class concept_f67c4c8e {
        <<logic>>
        name: 格式
    }
    class concept_7e17a33e {
        <<logic>>
        name: @符号
    }
    class concept_9bca5f1f {
        <<logic>>
        name: 最小值
    }
    class concept_665e51e4 {
        <<logic>>
        name: 0.01元
    }
    class concept_522d0a35 {
        <<logic>>
        name: 最大值
    }
    class concept_40cf8321 {
        <<logic>>
        name: 999999.99元
    }
    class concept_e6d19cbd {
        <<data>>
        name: 商品名称
    }
    class concept_7a2c8a1e {
        <<logic>>
        name: 长度
    }
    class concept_1a0fd1cf {
        <<logic>>
        name: 200个字符
    }
    class concept_1bdad7df {
        <<logic>>
        name: 收货地址
    }
    class concept_700b39b7 {
        <<logic>>
        name: 最长
    }
    class concept_9b593023 {
        <<logic>>
        name: 500个字符
    }
    class concept_6da995bc {
        <<logic>>
        name: 下单流程
    }
    class concept_53bac5d3 {
        <<logic>>
        name: 浏览商品
    }
    class concept_cb862c25 {
        <<logic>>
        name: 购物车
    }
    class concept_5ac79b96 {
        <<logic>>
        name: 仓库
    }
    class concept_24f74c41 {
        <<logic>>
        name: 拣货
    }
    class concept_86cd6bd9 {
        <<logic>>
        name: 退款流程
    }
    class concept_3af38e41 {
        <<logic>>
        name: 确认收货
    }
```