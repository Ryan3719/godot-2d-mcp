@tool
extends RefCounted


static func make(
	code: String,
	message: String,
	retryable: bool = false,
	hint: String = "",
	details: Dictionary = {}
) -> Dictionary:
	return {
		"_error": {
			"code": code,
			"message": message,
			"retryable": retryable,
			"hint": hint,
			"details": details,
		}
	}
