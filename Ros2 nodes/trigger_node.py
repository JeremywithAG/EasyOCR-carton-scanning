import rclpy

from rclpy.node import Node

from std_msgs.msg import String

import paho.mqtt.client as mqtt

import threading

import time



BROKER = "192.168.137.134"

TOPIC  = "camera/capture"

EXPECTED_DEVICES = {"1", "2", "3", "4", "5"}



class TriggerNode(Node):

    def __init__(self):

        super().__init__('trigger_node')



        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        self.mqtt_client.connect(BROKER, 1883, keepalive=60)

        self.mqtt_client.loop_start()



        # listen for trigger commands from any ROS node

        self.sub = self.create_subscription(

            String, '/scan/trigger', self.trigger_callback, 10)



        self.get_logger().info("Trigger node ready.")

        self.get_logger().info("Publish to /scan/trigger to fire cameras.")



    def trigger_callback(self, msg):

        payload = msg.data   # e.g. "1,2,3,4,5"

        self.mqtt_client.publish(TOPIC, payload, qos=1)

        self.get_logger().info(f"MQTT trigger sent → devices {payload}")



    def destroy_node(self):

        self.mqtt_client.loop_stop()

        self.mqtt_client.disconnect()

        super().destroy_node()



def main():

    rclpy.init()

    node = TriggerNode()

    try:

        rclpy.spin(node)

    except KeyboardInterrupt:

        pass

    finally:

        node.destroy_node()

        rclpy.shutdown()



if __name__ == "__main__":

    main()
