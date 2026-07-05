import { helper } from "./helper.mjs";

export async function handleThing(input) {
  const cwd = input.cwd || process.cwd();
  await helper(cwd);
  return cwd;
}

export function describeItem(item) {
  switch (item.type) {
    case "fileChange":
      return { message: `Applying ${item.changes.length} change(s).` };
    default:
      return item.deep != null ? `value ${item.a}` : `fallback ${item.b}`;
  }
}

//@@start smoke-section
export function teardown(session) {
  session.close();
  return true;
}
//@@end smoke-section
