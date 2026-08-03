@tool
extends VBoxContainer

var _connection: Node
var _status_label: Label
var _server_label: Label
var _endpoint_label: Label


func setup(connection: Node, ws_port: int) -> void:
	_connection = connection
	name = "Godot 2D MCP"
	custom_minimum_size = Vector2(280, 112)

	var title := Label.new()
	title.text = "Godot 2D MCP"
	title.add_theme_font_size_override("font_size", 16)
	add_child(title)

	_status_label = Label.new()
	_status_label.text = "Disconnected"
	add_child(_status_label)

	_server_label = Label.new()
	_server_label.text = "Server: -"
	add_child(_server_label)

	_endpoint_label = Label.new()
	_endpoint_label.text = "WebSocket: 127.0.0.1:%d" % ws_port
	add_child(_endpoint_label)

	connection.connection_state_changed.connect(_on_connection_state_changed)


func _on_connection_state_changed(connected: bool, server_version: String) -> void:
	_status_label.text = "Connected" if connected else "Disconnected"
	_server_label.text = "Server: %s" % (server_version if not server_version.is_empty() else "-")
