import rclpy

from rclpy.node import Node

from std_msgs.msg import String

import paho.mqtt.client as mqtt



BROKER       = "YOUR_IP"

RESULT_TOPIC = "scan/result"



class ResultBridgeNode(Node):

    def __init__(self):

        super().__init__('result_bridge_node')

        self.pub = self.create_publisher(String, '/scan/result', 10)

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        self.mqtt_client.on_connect = self.on_connect

        self.mqtt_client.on_message = self.on_message

        self.mqtt_client.connect(BROKER, 1883, keepalive=60)

        self.mqtt_client.loop_start()

        self.get_logger().info("Result bridge node ready.")



    def on_connect(self, client, userdata, flags, reason_code, properties):

        if reason_code == 0:

            client.subscribe(RESULT_TOPIC, qos=1)

            self.get_logger().info(f"Subscribed to MQTT topic: {RESULT_TOPIC}")

        else:

            self.get_logger().error(f"MQTT connect failed: {reason_code}")



    def on_message(self, client, userdata, msg):

        payload = msg.payload.decode().strip()

        self.get_logger().info(f"Result received: {payload}")

        self.pub.publish(String(data=payload))

        self.get_logger().info("Published to /scan/result")



    def destroy_node(self):

        self.mqtt_client.loop_stop()

        self.mqtt_client.disconnect()

        super().destroy_node()



def main():

    rclpy.init()

    node = ResultBridgeNode()

    try:

        rclpy.spin(node)

    except KeyboardInterrupt:

        pass

    finally:

        node.destroy_node()

        rclpy.shutdown()



if __name__ == "__main__":

    main()
