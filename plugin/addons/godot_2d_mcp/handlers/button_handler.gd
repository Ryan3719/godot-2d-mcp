@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_PROPERTIES := 32
const MAX_TEXT_LENGTH := 4096
const MAX_LANGUAGE_LENGTH := 128
const MAX_URI_LENGTH := 4096
const MAX_PATH_LENGTH := 4096
const MAX_MENU_ITEMS := 256
const MAX_MENU_ITEM_TOOLTIP_LENGTH := 1024
const MAX_MENU_ITEM_INDENT := 64
const MAX_MENU_ITEM_ICON_WIDTH := 4096
const MAX_MENU_ITEM_STATES := 256

const BASE_PROPERTIES := [
	"disabled", "toggle_mode", "button_pressed", "action_mode", "button_mask",
	"keep_pressed_outside", "shortcut_feedback", "shortcut_in_tooltip", "button_group_path",
	"shortcut_path",
]
const BUTTON_PROPERTIES := [
	"text", "icon_path", "flat", "alignment", "text_overrun_behavior", "autowrap_mode",
	"autowrap_trim_flags", "clip_text", "icon_alignment", "vertical_icon_alignment", "expand_icon",
	"text_direction", "language",
]
const LINK_BUTTON_PROPERTIES := [
	"text", "uri", "underline", "text_overrun_behavior", "ellipsis_char", "text_direction", "language",
]
const TEXTURE_BUTTON_PROPERTIES := [
	"texture_normal_path", "texture_pressed_path", "texture_hover_path", "texture_disabled_path",
	"texture_focused_path", "click_mask_path", "ignore_texture_size", "stretch_mode", "flip_h", "flip_v",
]
const PROPERTY_ORDER := [
	"disabled", "toggle_mode", "button_group", "button_pressed", "action_mode", "button_mask",
	"keep_pressed_outside", "shortcut_feedback", "shortcut_in_tooltip", "shortcut", "text", "icon", "flat",
	"alignment", "text_overrun_behavior", "autowrap_mode", "autowrap_trim_flags", "clip_text",
	"icon_alignment", "vertical_icon_alignment", "expand_icon", "text_direction", "language",
	"uri", "underline", "ellipsis_char",
	"texture_normal", "texture_pressed", "texture_hover", "texture_disabled", "texture_focused",
	"texture_click_mask", "ignore_texture_size", "stretch_mode", "flip_h", "flip_v",
]
const RESOURCE_PROPERTIES := {
	"button_group": true,
	"shortcut": true,
	"icon": true,
	"texture_normal": true,
	"texture_pressed": true,
	"texture_hover": true,
	"texture_disabled": true,
	"texture_focused": true,
	"texture_click_mask": true,
}
const ACTION_MODES := {"press": 0, "release": 1}
const BUTTON_MASKS := {"left": 1, "right": 2, "middle": 4}
const HORIZONTAL_ALIGNMENTS := {"left": 0, "center": 1, "right": 2}
const VERTICAL_ALIGNMENTS := {"top": 0, "center": 1, "bottom": 2}
const TEXT_OVERRUN_BEHAVIORS := {
	"no_trimming": 0,
	"trim_characters": 1,
	"trim_words": 2,
	"ellipsis": 3,
	"word_ellipsis": 4,
	"ellipsis_force": 5,
	"word_ellipsis_force": 6,
}
const AUTOWRAP_MODES := {"off": 0, "arbitrary": 1, "word": 2, "smart_word": 3}
const AUTOWRAP_TRIM_FLAGS := {"trim_start": 64, "trim_end": 128}
const TEXT_DIRECTIONS := {"auto": 0, "ltr": 1, "rtl": 2, "inherited": 3}
const LINK_UNDERLINE_MODES := {"always": 0, "on_hover": 1, "never": 2}
const AUTO_TRANSLATE_MODES := {"inherit": 0, "always": 1, "disabled": 2}
const TEXTURE_STRETCH_MODES := {
	"scale": 0,
	"tile": 1,
	"keep": 2,
	"keep_centered": 3,
	"keep_aspect": 4,
	"keep_aspect_centered": 5,
	"keep_aspect_covered": 6,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_button_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button(params, false)
	if resolved.has("_error"):
		return resolved
	return _button_response(resolved["button"], resolved["scene_root"])


func set_button_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button(params)
	if resolved.has("_error"):
		return resolved
	var button: BaseButton = resolved["button"]
	var parsed := _parse_updates(params, button)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_properties(button, parsed["updates"])
	if changed.is_empty():
		var unchanged := _button_response(button, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_updates(button, resolved["scene_root"], changed, "Update %s %s" % [button.get_class(), button.name])
	var result := _button_response(button, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_button_menu_items(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button_menu(params, false)
	if resolved.has("_error"):
		return resolved
	var page := _parse_menu_page(params)
	if page.has("_error"):
		return page
	return _menu_items_response(resolved, page["offset"], page["limit"])


func set_button_menu_items(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button_menu(params)
	if resolved.has("_error"):
		return resolved
	var submenu_validation := _validate_menu_has_no_submenus(resolved["popup"])
	if submenu_validation.has("_error"):
		return submenu_validation
	var parsed := _parse_button_menu_items(params, resolved["button"])
	if parsed.has("_error"):
		return parsed
	var current_items := _snapshot_button_menu_items(resolved["button"], resolved["popup"])
	var current_selected := _menu_selected_index(resolved["button"])
	var next_selected: int = parsed.get("selected_index", current_selected)
	if resolved["button"] is OptionButton and next_selected >= parsed["items"].size():
		next_selected = -1
	if current_items == parsed["items"] and current_selected == next_selected:
		var unchanged := _menu_items_response(resolved, 0, MAX_MENU_ITEMS)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_button_menu_items(resolved, current_items, parsed["items"], current_selected, next_selected)
	var result := _menu_items_response(resolved, 0, MAX_MENU_ITEMS)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_button_menu_items(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button_menu(params)
	if resolved.has("_error"):
		return resolved
	var submenu_validation := _validate_menu_has_no_submenus(resolved["popup"])
	if submenu_validation.has("_error"):
		return submenu_validation
	var current_items := _snapshot_button_menu_items(resolved["button"], resolved["popup"])
	if current_items.is_empty():
		var unchanged := _menu_items_response(resolved, 0, MAX_MENU_ITEMS)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_button_menu_items(
		resolved, current_items, [], _menu_selected_index(resolved["button"]), -1
	)
	var result := _menu_items_response(resolved, 0, MAX_MENU_ITEMS)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_button_menu(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_button(params, require_writable)
	if resolved.has("_error"):
		return resolved
	var button: BaseButton = resolved["button"]
	if not (button is OptionButton or button is MenuButton):
		return Errors.make(
			"BUTTON_MENU_REQUIRED",
			"Node '%s' is %s, not an OptionButton or MenuButton" % [button.name, button.get_class()],
			false,
			"Target an OptionButton or MenuButton."
		)
	var popup: PopupMenu = (button as OptionButton).get_popup() if button is OptionButton else (button as MenuButton).get_popup()
	if popup == null:
		return Errors.make("BUTTON_MENU_UNAVAILABLE", "The button has no editable PopupMenu")
	resolved["popup"] = popup
	return resolved


func _parse_menu_page(params: Dictionary) -> Dictionary:
	var offset_result := _parse_menu_integer(params.get("offset", 0), "offset", 0, MAX_MENU_ITEMS)
	if offset_result.has("_error"):
		return offset_result
	var limit_result := _parse_menu_integer(params.get("limit", 100), "limit", 1, MAX_MENU_ITEMS)
	if limit_result.has("_error"):
		return limit_result
	return {"offset": offset_result["value"], "limit": limit_result["value"]}


func _parse_button_menu_items(params: Dictionary, button: BaseButton) -> Dictionary:
	var raw_items: Variant = params.get("items", null)
	if not raw_items is Array or raw_items.is_empty() or raw_items.size() > MAX_MENU_ITEMS:
		return _invalid_menu_configuration(
			"items must be a non-empty array containing at most %d entries" % MAX_MENU_ITEMS
		)
	var items: Array = []
	for index in range(raw_items.size()):
		var parsed_item := _parse_button_menu_item(raw_items[index], index, button is OptionButton)
		if parsed_item.has("_error"):
			return parsed_item
		items.append(parsed_item["item"])
	var result := {"items": items}
	if params.has("selected_index"):
		if not button is OptionButton:
			return _invalid_menu_configuration("selected_index is only supported by OptionButton")
		var selected_result := _parse_menu_integer(
			params["selected_index"], "selected_index", -1, items.size() - 1
		)
		if selected_result.has("_error"):
			return selected_result
		result["selected_index"] = selected_result["value"]
	return result


func _parse_button_menu_item(raw_item: Variant, index: int, option_button: bool) -> Dictionary:
	if not raw_item is Dictionary:
		return _invalid_menu_configuration("items[%d] must be an object" % index)
	var kind_value: Variant = raw_item.get("kind", "normal")
	if not kind_value is String:
		return _invalid_menu_configuration("items[%d].kind must be a string" % index)
	var kind: String = kind_value.strip_edges().to_lower()
	if not kind in ["normal", "check", "radio", "multistate", "separator"]:
		return _invalid_menu_configuration("items[%d].kind is unsupported" % index)
	if option_button and not kind in ["normal", "separator"]:
		return _invalid_menu_configuration(
			"OptionButton only supports normal and separator menu items"
		)
	var allowed := _menu_item_allowed_fields(kind, option_button)
	for raw_key in raw_item:
		if not raw_key is String or not allowed.has(raw_key):
			return _invalid_menu_configuration(
				"items[%d] contains an unsupported %s field" % [index, "OptionButton" if option_button else "MenuButton"]
			)
	var text_result := _parse_string(raw_item.get("text", ""), "items[%d].text" % index, MAX_TEXT_LENGTH)
	if text_result.has("_error"):
		return text_result
	var id_result := _parse_menu_integer(
		raw_item.get("id", index), "items[%d].id" % index, -2147483648, 2147483647
	)
	if id_result.has("_error"):
		return id_result
	var item := {
		"kind": kind,
		"text": text_result["value"],
		"id": id_result["value"],
	}
	if kind == "separator":
		return {"item": item}
	var icon_result := _load_optional_resource(
		raw_item.get("icon_path", ""), "Texture2D", "items[%d].icon_path" % index, "icon"
	)
	if icon_result.has("_error"):
		return icon_result
	var metadata_result := VariantCodec.decode_json_value(raw_item.get("metadata", null))
	if metadata_result.has("_error"):
		return _invalid_menu_configuration("items[%d].metadata must be JSON-compatible" % index)
	var disabled_result := _parse_bool(raw_item.get("disabled", false), "items[%d].disabled" % index)
	if disabled_result.has("_error"):
		return disabled_result
	var tooltip_result := _parse_string(
		raw_item.get("tooltip", ""), "items[%d].tooltip" % index, MAX_MENU_ITEM_TOOLTIP_LENGTH
	)
	if tooltip_result.has("_error"):
		return tooltip_result
	item["icon"] = icon_result["value"]
	item["metadata"] = metadata_result["value"]
	item["disabled"] = disabled_result["value"]
	item["tooltip"] = tooltip_result["value"]
	if option_button:
		return {"item": item}
	var accelerator_result := _parse_menu_integer(
		raw_item.get("accelerator", 0), "items[%d].accelerator" % index, 0, 2147483647
	)
	if accelerator_result.has("_error"):
		return accelerator_result
	var indent_result := _parse_menu_integer(
		raw_item.get("indent", 0), "items[%d].indent" % index, 0, MAX_MENU_ITEM_INDENT
	)
	if indent_result.has("_error"):
		return indent_result
	var direction_result := _parse_enum(
		raw_item.get("text_direction", "auto"), "items[%d].text_direction" % index, TEXT_DIRECTIONS
	)
	if direction_result.has("_error"):
		return direction_result
	var language_result := _parse_string(
		raw_item.get("language", ""), "items[%d].language" % index, MAX_LANGUAGE_LENGTH
	)
	if language_result.has("_error"):
		return language_result
	var translation_result := _parse_enum(
		raw_item.get("auto_translate_mode", "inherit"), "items[%d].auto_translate_mode" % index, AUTO_TRANSLATE_MODES
	)
	if translation_result.has("_error"):
		return translation_result
	var icon_width_result := _parse_menu_integer(
		raw_item.get("icon_max_width", 0), "items[%d].icon_max_width" % index, 0, MAX_MENU_ITEM_ICON_WIDTH
	)
	if icon_width_result.has("_error"):
		return icon_width_result
	var color_result := _parse_menu_color(raw_item.get("icon_modulate", Color.WHITE), index)
	if color_result.has("_error"):
		return color_result
	item["accelerator"] = accelerator_result["value"]
	item["indent"] = indent_result["value"]
	item["text_direction"] = direction_result["value"]
	item["language"] = language_result["value"]
	item["auto_translate_mode"] = translation_result["value"]
	item["icon_max_width"] = icon_width_result["value"]
	item["icon_modulate"] = color_result["value"]
	if kind in ["check", "radio"]:
		var checked_result := _parse_bool(raw_item.get("checked", false), "items[%d].checked" % index)
		if checked_result.has("_error"):
			return checked_result
		item["checked"] = checked_result["value"]
	if kind == "multistate":
		var max_states_result := _parse_menu_integer(
			raw_item.get("max_states", null), "items[%d].max_states" % index, 2, MAX_MENU_ITEM_STATES
		)
		if max_states_result.has("_error"):
			return max_states_result
		var state_result := _parse_menu_integer(
			raw_item.get("state", 0), "items[%d].state" % index, 0, max_states_result["value"] - 1
		)
		if state_result.has("_error"):
			return state_result
		item["max_states"] = max_states_result["value"]
		item["state"] = state_result["value"]
	return {"item": item}


func _menu_item_allowed_fields(kind: String, option_button: bool) -> Dictionary:
	if kind == "separator":
		return {"kind": true, "text": true, "id": true}
	var fields := {
		"kind": true, "text": true, "id": true, "icon_path": true, "metadata": true,
		"disabled": true, "tooltip": true,
	}
	if option_button:
		return fields
	for name_value in [
		"accelerator", "indent",
		"text_direction", "language", "auto_translate_mode", "icon_max_width", "icon_modulate",
	]:
		fields[str(name_value)] = true
	if kind in ["check", "radio"]:
		fields["checked"] = true
	if kind == "multistate":
		fields["max_states"] = true
		fields["state"] = true
	return fields


func _parse_menu_integer(raw_value: Variant, label: String, minimum: int, maximum: int) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool \
		or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)):
		return _invalid_menu_configuration("%s must be an integer" % label)
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return _invalid_menu_configuration("%s must be between %d and %d" % [label, minimum, maximum])
	return {"value": value}


func _parse_menu_color(raw_value: Variant, index: int) -> Dictionary:
	if raw_value is Color:
		if _is_finite_color(raw_value):
			return {"value": raw_value}
		return _invalid_menu_configuration("items[%d].icon_modulate must be a finite Color" % index)
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
	if decoded.has("_error") or not _is_finite_color(decoded.get("value", Color.WHITE)):
		return _invalid_menu_configuration("items[%d].icon_modulate must be a finite Color" % index)
	return {"value": decoded["value"]}


func _is_finite_color(value: Color) -> bool:
	return is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)


func _validate_menu_has_no_submenus(popup: PopupMenu) -> Dictionary:
	for index in range(popup.get_item_count()):
		if popup.get_item_submenu_node(index) != null or not popup.get_item_submenu(index).is_empty():
			return Errors.make(
				"BUTTON_MENU_SUBMENU_UNSUPPORTED",
				"Menu contains a submenu at item %d" % index,
				false,
				"Nested PopupMenu editing is not available yet; edit a flat menu or preserve it unchanged."
			)
		if popup.get_item_shortcut(index) != null:
			return Errors.make(
				"BUTTON_MENU_ITEM_SHORTCUT_UNSUPPORTED",
				"Menu contains a Shortcut resource at item %d" % index,
				false,
				"Godot does not serialize MenuButton item Shortcut resources; use an accelerator instead."
			)
	return {}


func _snapshot_button_menu_items(button: BaseButton, popup: PopupMenu) -> Array:
	if button is OptionButton:
		return _snapshot_option_button_items(button as OptionButton)
	return _snapshot_popup_menu_items(popup)


func _snapshot_option_button_items(button: OptionButton) -> Array:
	var items: Array = []
	for index in range(button.get_item_count()):
		var item := {
			"kind": "separator" if button.is_item_separator(index) else "normal",
			"text": button.get_item_text(index),
			"id": button.get_item_id(index),
		}
		if item["kind"] == "normal":
			item["icon"] = button.get_item_icon(index)
			item["metadata"] = button.get_item_metadata(index)
			item["disabled"] = button.is_item_disabled(index)
			item["tooltip"] = button.get_item_tooltip(index)
		items.append(item)
	return items


func _snapshot_popup_menu_items(popup: PopupMenu) -> Array:
	var items: Array = []
	for index in range(popup.get_item_count()):
		var kind := "normal"
		if popup.is_item_separator(index):
			kind = "separator"
		elif popup.is_item_radio_checkable(index):
			kind = "radio"
		elif popup.is_item_checkable(index):
			kind = "check"
		elif popup.get_item_multistate_max(index) > 0:
			kind = "multistate"
		var item := {
			"kind": kind,
			"text": popup.get_item_text(index),
			"id": popup.get_item_id(index),
		}
		if kind == "separator":
			items.append(item)
			continue
		item["icon"] = popup.get_item_icon(index)
		item["metadata"] = popup.get_item_metadata(index)
		item["disabled"] = popup.is_item_disabled(index)
		item["tooltip"] = popup.get_item_tooltip(index)
		item["accelerator"] = int(popup.get_item_accelerator(index))
		item["indent"] = popup.get_item_indent(index)
		item["text_direction"] = int(popup.get_item_text_direction(index))
		item["language"] = popup.get_item_language(index)
		item["auto_translate_mode"] = int(popup.get_item_auto_translate_mode(index))
		item["icon_max_width"] = popup.get_item_icon_max_width(index)
		item["icon_modulate"] = popup.get_item_icon_modulate(index)
		if kind in ["check", "radio"]:
			item["checked"] = popup.is_item_checked(index)
		if kind == "multistate":
			item["max_states"] = popup.get_item_multistate_max(index)
			item["state"] = popup.get_item_multistate(index)
		items.append(item)
	return items


func _menu_selected_index(button: BaseButton) -> int:
	if button is OptionButton:
		return (button as OptionButton).get_selected()
	return -1


func _commit_button_menu_items(
	resolved: Dictionary,
	previous_items: Array,
	next_items: Array,
	previous_selected: int,
	next_selected: int
) -> void:
	var button: BaseButton = resolved["button"]
	var popup: PopupMenu = resolved["popup"]
	var scene_root: Node = resolved["scene_root"]
	_undo_redo.create_action(
		"Godot 2D MCP: Replace %s menu items" % button.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	if button is OptionButton:
		_undo_redo.add_do_method(self, "_replace_option_button_items", button, next_items, next_selected)
		_undo_redo.add_undo_method(
			self, "_replace_option_button_items", button, previous_items, previous_selected
		)
	else:
		_undo_redo.add_do_method(self, "_replace_popup_menu_items", popup, next_items)
		_undo_redo.add_undo_method(self, "_replace_popup_menu_items", popup, previous_items)
	_add_menu_resource_references(next_items, true)
	_add_menu_resource_references(previous_items, false)
	_undo_redo.commit_action()


func _add_menu_resource_references(items: Array, do_reference: bool) -> void:
	for item in items:
		if not item is Dictionary:
			continue
		for property_name in ["icon"]:
			var resource: Variant = item.get(property_name, null)
			if not resource is Resource:
				continue
			if do_reference:
				_undo_redo.add_do_reference(resource)
			else:
				_undo_redo.add_undo_reference(resource)


func _replace_option_button_items(button: OptionButton, items: Array, selected_index: int) -> void:
	button.clear()
	for item in items:
		var index := button.get_item_count()
		if item["kind"] == "separator":
			button.add_separator(item["text"])
		else:
			var icon: Texture2D = item["icon"]
			if icon == null:
				button.add_item(item["text"], item["id"])
			else:
				button.add_icon_item(icon, item["text"], item["id"])
			button.set_item_metadata(index, item["metadata"])
			button.set_item_disabled(index, item["disabled"])
			button.set_item_tooltip(index, item["tooltip"])
		button.set_item_id(index, item["id"])
	button.select(selected_index)


func _replace_popup_menu_items(popup: PopupMenu, items: Array) -> void:
	popup.clear(false)
	for item in items:
		_add_popup_menu_item(popup, item)


func _add_popup_menu_item(popup: PopupMenu, item: Dictionary) -> void:
	var index := popup.get_item_count()
	if item["kind"] == "separator":
		popup.add_separator(item["text"], item["id"])
		return
	var icon: Texture2D = item["icon"]
	match item["kind"]:
		"check":
			if icon == null:
				popup.add_check_item(item["text"], item["id"], item["accelerator"])
			else:
				popup.add_icon_check_item(icon, item["text"], item["id"], item["accelerator"])
		"radio":
			if icon == null:
				popup.add_radio_check_item(item["text"], item["id"], item["accelerator"])
			else:
				popup.add_icon_radio_check_item(icon, item["text"], item["id"], item["accelerator"])
		"multistate":
			popup.add_multistate_item(
				item["text"], item["max_states"], item["state"], item["id"], item["accelerator"]
			)
			if icon != null:
				popup.set_item_icon(index, icon)
		_:
			if icon == null:
				popup.add_item(item["text"], item["id"], item["accelerator"])
			else:
				popup.add_icon_item(icon, item["text"], item["id"], item["accelerator"])
	popup.set_item_metadata(index, item["metadata"])
	popup.set_item_disabled(index, item["disabled"])
	popup.set_item_tooltip(index, item["tooltip"])
	popup.set_item_indent(index, item["indent"])
	popup.set_item_text_direction(index, item["text_direction"])
	popup.set_item_language(index, item["language"])
	popup.set_item_auto_translate_mode(index, item["auto_translate_mode"])
	popup.set_item_icon_max_width(index, item["icon_max_width"])
	popup.set_item_icon_modulate(index, item["icon_modulate"])
	if item["kind"] in ["check", "radio"]:
		popup.set_item_checked(index, item["checked"])


func _menu_items_response(resolved: Dictionary, offset: int, limit: int) -> Dictionary:
	var button: BaseButton = resolved["button"]
	var items := _snapshot_button_menu_items(button, resolved["popup"])
	var start := min(offset, items.size())
	var end := min(start + limit, items.size())
	var serialized: Array = []
	for index in range(start, end):
		serialized.append(_serialize_button_menu_item(items[index], button is OptionButton))
	var result := {
		"path": ScenePath.from_node(button, resolved["scene_root"]),
		"type": button.get_class(),
		"item_count": items.size(),
		"item_offset": start,
		"items": serialized,
		"items_truncated": end < items.size(),
		"supported_item_kinds": ["normal", "separator"] if button is OptionButton else [
			"normal", "check", "radio", "multistate", "separator"
		],
	}
	if button is OptionButton:
		var option_button := button as OptionButton
		result["selected_index"] = option_button.get_selected()
		result["selected_id"] = option_button.get_selected_id()
		result["fit_to_longest_item"] = option_button.is_fit_to_longest_item()
		result["allow_reselect"] = option_button.get_allow_reselect()
	return result


func _serialize_button_menu_item(item: Dictionary, option_button: bool) -> Dictionary:
	var serialized := {
		"kind": item["kind"],
		"text": item["text"],
		"id": item["id"],
	}
	if item["kind"] == "separator":
		return serialized
	serialized["icon"] = _resource_descriptor(item["icon"])
	serialized["metadata"] = VariantCodec.serialize(item["metadata"])
	serialized["disabled"] = item["disabled"]
	serialized["tooltip"] = item["tooltip"]
	if option_button:
		return serialized
	serialized["accelerator"] = item["accelerator"]
	serialized["indent"] = item["indent"]
	serialized["text_direction"] = _enum_name(item["text_direction"], TEXT_DIRECTIONS)
	serialized["language"] = item["language"]
	serialized["auto_translate_mode"] = _enum_name(item["auto_translate_mode"], AUTO_TRANSLATE_MODES)
	serialized["icon_max_width"] = item["icon_max_width"]
	serialized["icon_modulate"] = VariantCodec.serialize(item["icon_modulate"])
	if item["kind"] in ["check", "radio"]:
		serialized["checked"] = item["checked"]
	if item["kind"] == "multistate":
		serialized["max_states"] = item["max_states"]
		serialized["state"] = item["state"]
	return serialized


func _invalid_menu_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_BUTTON_MENU_CONFIGURATION", message)


func _resolve_button(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var path := str(params.get("path", "")).strip_edges()
	if path.is_empty():
		return Errors.make("MISSING_PARAMETER", "path is required")
	var node := ScenePath.resolve(path, scene_root)
	if node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Node not found: %s" % path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is BaseButton:
		return Errors.make(
			"BASE_BUTTON_REQUIRED",
			"Node '%s' is %s, not a BaseButton" % [node.name, node.get_class()],
			false,
			"Target a Button, TextureButton, LinkButton, CheckButton, OptionButton, or MenuButton."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit button '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned button."
		)
	return {"button": node as BaseButton, "scene_root": scene_root}


func _parse_updates(params: Dictionary, button: BaseButton) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return _invalid_configuration(
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var allowed := _supported_properties(button)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not allowed.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_BUTTON_PROPERTY",
				"Unsupported %s property: %s" % [button.get_class(), str(raw_name)],
				false,
				"Call button_2d_get to inspect supported_properties for this node type."
			)
		var value_result := _parse_property_value(raw_name, raw_properties[raw_name])
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	var validation := _validate_configuration(button, updates)
	if validation.has("_error"):
		return validation
	return {"updates": updates}


func _parse_property_value(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"disabled", "toggle_mode", "button_pressed", "keep_pressed_outside", "shortcut_feedback", \
		"shortcut_in_tooltip", "flat", "clip_text", "expand_icon", "ignore_texture_size", "flip_h", "flip_v":
			return _parse_bool(raw_value, name)
		"action_mode":
			return _parse_enum(raw_value, name, ACTION_MODES)
		"button_mask":
			return _parse_button_mask(raw_value)
		"button_group_path":
			return _load_optional_resource(raw_value, "ButtonGroup", name, "button_group")
		"shortcut_path":
			return _load_optional_resource(raw_value, "Shortcut", name, "shortcut")
		"text":
			return _parse_string(raw_value, name, MAX_TEXT_LENGTH)
		"uri":
			return _parse_string(raw_value, name, MAX_URI_LENGTH)
		"underline":
			return _parse_enum(raw_value, name, LINK_UNDERLINE_MODES)
		"ellipsis_char":
			return _parse_ellipsis_char(raw_value)
		"icon_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "icon")
		"alignment", "icon_alignment":
			return _parse_enum(raw_value, name, HORIZONTAL_ALIGNMENTS)
		"vertical_icon_alignment":
			return _parse_enum(raw_value, name, VERTICAL_ALIGNMENTS)
		"text_overrun_behavior":
			return _parse_enum(raw_value, name, TEXT_OVERRUN_BEHAVIORS)
		"autowrap_mode":
			return _parse_enum(raw_value, name, AUTOWRAP_MODES)
		"autowrap_trim_flags":
			return _parse_autowrap_trim_flags(raw_value)
		"text_direction":
			return _parse_enum(raw_value, name, TEXT_DIRECTIONS)
		"language":
			return _parse_string(raw_value, name, MAX_LANGUAGE_LENGTH)
		"texture_normal_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_normal")
		"texture_pressed_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_pressed")
		"texture_hover_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_hover")
		"texture_disabled_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_disabled")
		"texture_focused_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_focused")
		"click_mask_path":
			return _load_optional_resource(raw_value, "BitMap", name, "texture_click_mask")
		"stretch_mode":
			return _parse_enum(raw_value, name, TEXTURE_STRETCH_MODES)
	return _invalid_configuration("Unsupported button property: %s" % name)


func _validate_configuration(button: BaseButton, updates: Dictionary) -> Dictionary:
	var toggle_mode := bool(updates.get("toggle_mode", button.is_toggle_mode()))
	var pressed := bool(updates.get("button_pressed", button.is_pressed()))
	if pressed and not toggle_mode:
		return _invalid_configuration("button_pressed requires toggle_mode to be true")
	return {}


func _parse_bool(raw_value: Variant, property_name: String) -> Dictionary:
	if not raw_value is bool:
		return _invalid_configuration("%s must be a boolean" % property_name)
	return {"property_name": property_name, "value": raw_value}


func _parse_string(raw_value: Variant, property_name: String, maximum_length: int) -> Dictionary:
	if not raw_value is String or raw_value.length() > maximum_length:
		return _invalid_configuration("%s must be a string up to %d characters" % [property_name, maximum_length])
	return {"property_name": property_name, "value": raw_value}


func _parse_ellipsis_char(raw_value: Variant) -> Dictionary:
	if not raw_value is String or raw_value.length() != 1:
		return _invalid_configuration("ellipsis_char must contain exactly one character")
	return {"property_name": "ellipsis_char", "value": raw_value}


func _parse_enum(raw_value: Variant, property_name: String, values: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	var name: String = raw_value.strip_edges().to_lower()
	if not values.has(name):
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	return {"property_name": property_name, "value": values[name]}


func _parse_button_mask(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > BUTTON_MASKS.size():
		return _invalid_configuration("button_mask must contain unique left, right, or middle button names")
	var mask := 0
	var seen := {}
	for raw_name in raw_value:
		if not raw_name is String:
			return _invalid_configuration("button_mask must contain unique left, right, or middle button names")
		var name: String = raw_name.strip_edges().to_lower()
		if not BUTTON_MASKS.has(name) or seen.has(name):
			return _invalid_configuration("button_mask must contain unique left, right, or middle button names")
		seen[name] = true
		mask |= int(BUTTON_MASKS[name])
	return {"property_name": "button_mask", "value": mask}


func _parse_autowrap_trim_flags(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > AUTOWRAP_TRIM_FLAGS.size():
		return _invalid_configuration("autowrap_trim_flags must contain unique trim_start or trim_end names")
	var flags := 0
	var seen := {}
	for raw_name in raw_value:
		if not raw_name is String:
			return _invalid_configuration("autowrap_trim_flags must contain unique trim_start or trim_end names")
		var name: String = raw_name.strip_edges().to_lower()
		if not AUTOWRAP_TRIM_FLAGS.has(name) or seen.has(name):
			return _invalid_configuration("autowrap_trim_flags must contain unique trim_start or trim_end names")
		seen[name] = true
		flags |= int(AUTOWRAP_TRIM_FLAGS[name])
	return {"property_name": "autowrap_trim_flags", "value": flags}


func _load_optional_resource(
	raw_value: Variant, expected_type: String, input_name: String, property_name: String
) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be a res:// string or an empty string" % input_name)
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty():
		return {"property_name": property_name, "value": null}
	if resource_path.length() > MAX_PATH_LENGTH or not resource_path.begins_with("res://") \
		or resource_path.contains("/../") or resource_path.ends_with("/.."):
		return _invalid_configuration("%s must remain inside the project res:// directory" % input_name)
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "Resource does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource.is_class(expected_type):
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"%s must load %s" % [input_name, expected_type],
			false,
			"Use an existing project-local %s resource." % expected_type
		)
	return {"property_name": property_name, "value": resource}


func _changed_properties(button: BaseButton, updates: Dictionary) -> Dictionary:
	var changed := {}
	for property_name_value in PROPERTY_ORDER:
		var property_name := str(property_name_value)
		if updates.has(property_name) and button.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	return changed


func _commit_updates(button: BaseButton, scene_root: Node, updates: Dictionary, action_label: String) -> void:
	_undo_redo.create_action("Godot 2D MCP: %s" % action_label, UndoRedo.MERGE_DISABLE, scene_root, true)
	for property_name_value in PROPERTY_ORDER:
		var property_name := str(property_name_value)
		if not updates.has(property_name):
			continue
		var old_value = button.get(property_name)
		var new_value = updates[property_name]
		_undo_redo.add_do_property(button, property_name, new_value)
		if RESOURCE_PROPERTIES.has(property_name) and new_value is Resource:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(button, property_name, old_value)
		if RESOURCE_PROPERTIES.has(property_name) and old_value is Resource:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()


func _button_response(button: BaseButton, scene_root: Node) -> Dictionary:
	var configuration := {
		"disabled": button.is_disabled(),
		"toggle_mode": button.is_toggle_mode(),
		"button_pressed": button.is_pressed(),
		"action_mode": _enum_name(int(button.get_action_mode()), ACTION_MODES),
		"button_mask": _serialize_button_mask(int(button.get_button_mask())),
		"keep_pressed_outside": button.is_keep_pressed_outside(),
		"shortcut_feedback": button.is_shortcut_feedback(),
		"shortcut_in_tooltip": button.is_shortcut_in_tooltip_enabled(),
		"button_group": _resource_descriptor(button.get_button_group()),
		"shortcut": _resource_descriptor(button.get_shortcut()),
		"draw_mode": _draw_mode_name(int(button.get_draw_mode())),
	}
	if button is Button:
		configuration["button"] = _serialize_text_button(button as Button)
	if button is TextureButton:
		configuration["texture_button"] = _serialize_texture_button(button as TextureButton)
	if button is LinkButton:
		configuration["link_button"] = _serialize_link_button(button as LinkButton)
	return {
		"path": ScenePath.from_node(button, scene_root),
		"type": button.get_class(),
		"configuration": configuration,
		"supported_properties": _supported_properties(button),
	}


func _serialize_text_button(button: Button) -> Dictionary:
	return {
		"text": button.get_text(),
		"icon": _resource_descriptor(button.get_button_icon()),
		"flat": button.is_flat(),
		"alignment": _enum_name(int(button.get_text_alignment()), HORIZONTAL_ALIGNMENTS),
		"text_overrun_behavior": _enum_name(
			int(button.get_text_overrun_behavior()), TEXT_OVERRUN_BEHAVIORS
		),
		"autowrap_mode": _enum_name(int(button.get_autowrap_mode()), AUTOWRAP_MODES),
		"autowrap_trim_flags": _serialize_autowrap_trim_flags(int(button.get_autowrap_trim_flags())),
		"clip_text": button.get_clip_text(),
		"icon_alignment": _enum_name(int(button.get_icon_alignment()), HORIZONTAL_ALIGNMENTS),
		"vertical_icon_alignment": _enum_name(
			int(button.get_vertical_icon_alignment()), VERTICAL_ALIGNMENTS
		),
		"expand_icon": button.is_expand_icon(),
		"text_direction": _enum_name(int(button.get_text_direction()), TEXT_DIRECTIONS),
		"language": button.get_language(),
	}


func _serialize_texture_button(button: TextureButton) -> Dictionary:
	return {
		"texture_normal": _resource_descriptor(button.get_texture_normal()),
		"texture_pressed": _resource_descriptor(button.get_texture_pressed()),
		"texture_hover": _resource_descriptor(button.get_texture_hover()),
		"texture_disabled": _resource_descriptor(button.get_texture_disabled()),
		"texture_focused": _resource_descriptor(button.get_texture_focused()),
		"click_mask": _resource_descriptor(button.get_click_mask()),
		"ignore_texture_size": button.get_ignore_texture_size(),
		"stretch_mode": _enum_name(int(button.get_stretch_mode()), TEXTURE_STRETCH_MODES),
		"flip_h": button.is_flipped_h(),
		"flip_v": button.is_flipped_v(),
	}


func _serialize_link_button(button: LinkButton) -> Dictionary:
	return {
		"text": button.get_text(),
		"uri": button.get_uri(),
		"underline": _enum_name(int(button.get_underline_mode()), LINK_UNDERLINE_MODES),
		"text_overrun_behavior": _enum_name(
			int(button.get_text_overrun_behavior()), TEXT_OVERRUN_BEHAVIORS
		),
		"ellipsis_char": button.get_ellipsis_char(),
		"text_direction": _enum_name(int(button.get_text_direction()), TEXT_DIRECTIONS),
		"language": button.get_language(),
	}


func _resource_descriptor(resource: Resource) -> Dictionary:
	if resource == null:
		return {"assigned": false, "origin": "none", "resource_path": "", "resource_type": ""}
	return {
		"assigned": true,
		"origin": "external" if not resource.resource_path.is_empty() else "embedded",
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
	}


func _supported_properties(button: BaseButton) -> Array:
	var properties: Array = BASE_PROPERTIES.duplicate()
	if button is Button:
		properties.append_array(BUTTON_PROPERTIES)
	if button is TextureButton:
		properties.append_array(TEXTURE_BUTTON_PROPERTIES)
	if button is LinkButton:
		properties.append_array(LINK_BUTTON_PROPERTIES)
	return properties


func _serialize_button_mask(mask: int) -> Array[String]:
	var names: Array[String] = []
	for name_value in ["left", "right", "middle"]:
		var name: String = name_value
		if mask & int(BUTTON_MASKS[name]):
			names.append(name)
	return names


func _serialize_autowrap_trim_flags(flags: int) -> Array[String]:
	var names: Array[String] = []
	for name_value in ["trim_start", "trim_end"]:
		var name: String = name_value
		if flags & int(AUTOWRAP_TRIM_FLAGS[name]):
			names.append(name)
	return names


func _draw_mode_name(draw_mode: int) -> String:
	match draw_mode:
		0:
			return "normal"
		1:
			return "pressed"
		2:
			return "hover"
		3:
			return "disabled"
		4:
			return "hover_pressed"
	return "unknown"


func _enum_name(value: int, values: Dictionary) -> String:
	for name in values:
		if int(values[name]) == value:
			return str(name)
	return "unknown"


func _enum_options(values: Dictionary) -> String:
	var names: Array[String] = []
	for name in values:
		names.append(str(name))
	names.sort()
	return ", ".join(names)


func _invalid_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_BUTTON_CONFIGURATION", message)
