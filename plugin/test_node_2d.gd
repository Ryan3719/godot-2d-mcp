extends Node2D

@export var agent_label := "scripted"
@export var accent_colors: Array[Color] = []
@export var color_labels: Dictionary[String, Color] = {}
@export var color_lookup: Dictionary[Color, String] = {}
@export var icon_textures: Array[Texture2D] = []
@export var node_references: Array[Node] = []
