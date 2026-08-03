@tool
extends Node

signal connection_state_changed(connected: bool, server_version: String)

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")

const PROTOCOL_VERSION := 1
const INITIAL_RECONNECT_DELAY := 0.5
const MAX_RECONNECT_DELAY := 8.0
const MAX_PACKET_SIZE_BYTES := 2 * 1024 * 1024

var dispatcher: RefCounted
var plugin_version := "0.0.0"
var ws_port := 9500
var server_version := ""
var is_connected := false

var _peer := WebSocketPeer.new()
var _session_id := ""
var _reconnect_delay := INITIAL_RECONNECT_DELAY
var _reconnect_remaining := 0.0
var _last_state_signature := ""
var _scene_revision := 0
var _stopping := false


func _ready() -> void:
	_session_id = _make_session_id()
	_configure_peer()
	_connect_to_server()


func _process(delta: float) -> void:
	if _stopping:
		return
	_peer.poll()
	match _peer.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if not is_connected:
				is_connected = true
				_reconnect_delay = INITIAL_RECONNECT_DELAY
				_send_handshake()
				connection_state_changed.emit(true, server_version)
			_drain_packets()
			_emit_state_change_if_needed()
			if dispatcher != null:
				for response in dispatcher.tick(_response_meta()):
					_send_json(response)
		WebSocketPeer.STATE_CLOSED:
			if is_connected:
				is_connected = false
				server_version = ""
				connection_state_changed.emit(false, "")
			_reconnect_remaining -= delta
			if _reconnect_remaining <= 0.0:
				_connect_to_server()
		WebSocketPeer.STATE_CONNECTING, WebSocketPeer.STATE_CLOSING:
			pass


func teardown() -> void:
	_stopping = true
	set_process(false)
	if _peer.get_ready_state() == WebSocketPeer.STATE_OPEN:
		_peer.close(1000, "Plugin disabled")
	is_connected = false
	dispatcher = null


func _configure_peer() -> void:
	_peer.inbound_buffer_size = MAX_PACKET_SIZE_BYTES
	_peer.outbound_buffer_size = MAX_PACKET_SIZE_BYTES
	_peer.max_queued_packets = 64


func _connect_to_server() -> void:
	_peer = WebSocketPeer.new()
	_configure_peer()
	var error := _peer.connect_to_url("ws://127.0.0.1:%d" % ws_port)
	if error != OK:
		_reconnect_remaining = _reconnect_delay
		_reconnect_delay = minf(_reconnect_delay * 2.0, MAX_RECONNECT_DELAY)
		return
	_reconnect_remaining = _reconnect_delay
	_reconnect_delay = minf(_reconnect_delay * 2.0, MAX_RECONNECT_DELAY)


func _drain_packets() -> void:
	var drained := 0
	while _peer.get_available_packet_count() > 0 and drained < 64:
		var raw := _peer.get_packet().get_string_from_utf8()
		_handle_message(raw)
		drained += 1


func _handle_message(raw: String) -> void:
	var message = JSON.parse_string(raw)
	if not message is Dictionary:
		return
	match str(message.get("type", "")):
		"handshake_ack":
			server_version = str(message.get("server_version", ""))
			connection_state_changed.emit(true, server_version)
		"command":
			if dispatcher == null:
				return
			var error: Dictionary = dispatcher.enqueue(message)
			if error.has("_error"):
				_send_json(
					{
						"type": "response",
						"request_id": str(message.get("request_id", "")),
						"status": "error",
						"data": {},
						"error": error["_error"],
						"meta": _response_meta(),
					}
				)


func _send_handshake() -> void:
	var state := EditorState.snapshot()
	_send_json(
		{
			"type": "handshake",
			"protocol_version": PROTOCOL_VERSION,
			"session_id": _session_id,
			"plugin_version": plugin_version,
			"godot_version": state["godot_version"],
			"project_name": state["project_name"],
			"project_path": state["project_path"],
			"editor_pid": OS.get_process_id(),
			"readiness": state["readiness"],
			"current_scene": state["current_scene"],
			"play_state": state["play_state"],
		}
	)


func _emit_state_change_if_needed() -> void:
	var state := EditorState.snapshot()
	var signature := "%s|%s|%s" % [
		state["readiness"], state["current_scene"], state["play_state"]
	]
	if signature == _last_state_signature:
		return
	if not _last_state_signature.is_empty() and state["current_scene"] != _current_scene_from_signature():
		_scene_revision += 1
	_last_state_signature = signature
	_send_json(
		{
			"type": "state_changed",
			"readiness": state["readiness"],
			"current_scene": state["current_scene"],
			"play_state": state["play_state"],
			"scene_revision": _scene_revision,
		}
	)


func _current_scene_from_signature() -> String:
	var parts := _last_state_signature.split("|", false, 2)
	return parts[1] if parts.size() > 1 else ""


func _response_meta() -> Dictionary:
	return {
		"session_id": _session_id,
		"readiness": EditorState.readiness(),
		"scene_revision": _scene_revision,
	}


func _send_json(payload: Dictionary) -> void:
	if _peer.get_ready_state() == WebSocketPeer.STATE_OPEN:
		_peer.send_text(JSON.stringify(payload))


func _make_session_id() -> String:
	var project_path := ProjectSettings.globalize_path("res://").trim_suffix("/")
	var slug := project_path.get_file().to_lower().replace(" ", "-")
	var cleaned := ""
	for character in slug:
		if character.to_lower() != character.to_upper() or character.is_valid_int() or character in ["-", "_", "."]:
			cleaned += character
	if cleaned.is_empty():
		cleaned = "godot-project"
	var suffix := "%04x" % (Time.get_ticks_usec() & 0xFFFF)
	return "%s@%s" % [cleaned.left(100), suffix]
