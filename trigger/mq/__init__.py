"""MQ 触发层占位包（阶段 4 余项，待开发）。

未来在此实现消息队列消费入口（RabbitMQ / Kafka / SQS 等），
与 ``trigger.http``、``trigger.cli`` 保持同一触发契约：
消息反序列化 -> 参数校验 -> 复用 ``app`` 用例（``ParseDocumentUseCase``）。

依赖的端口契约已在 ``domain.ports.EventPublisherPort`` 声明（占位）；
具体 MQ 适配器实现放在 ``infra`` 层，组合根（``app/bootstrap.py``）负责装配。
"""

# TODO(阶段 4)：实现 MQ consumer：
#   1. 定义消息 schema（与 api/dto.py 对齐或新增 trigger/mq/dto.py）。
#   2. 实现一个或多个消费者函数，接收消息并调用用例。
#   3. 在 infra 实现 EventPublisherPort（例如 aiormq/kafka-python 适配器）。
#   4. 在 app/bootstrap.py 组合根注入事件发布器，并在用例中发布领域事件。