import { System } from "@/types/System";

export function indexSystemFromSchemaPath(
  system: System,
  schemaPath: Array<string> | string
) {
  let indices: Array<string>;
  let component: any;

  if (!Array.isArray(schemaPath)) {
    indices = schemaPath.split("/");
  } else {
    indices = [...schemaPath];
  }
  if (indices[0] == "") {
    // Pop an empty string, which can occur when "" or "/" is passed
    indices.shift();
  }
  if (!indices.length) {
    throw new Error("Invalid System Index: Empty");
  }
  component = system;

  while (indices.length) {
    // @ts-expect-error
    const index: string | number = indices.shift();

    try {
      component = component[index];
    } catch (error) {
      // Handle if index does not exist in component, should only occur if system
      // parameter is null/undefined
      throw new error("invalid system index");
    }
    // If value is null/undefined index was invalid
    if (component == null) {
      throw new Error("Invalid System Index");
    }
  }
  return component;
}