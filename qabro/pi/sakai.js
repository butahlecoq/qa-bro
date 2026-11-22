import { Type } from "typebox";
import { StringEnum } from "@earendil-works/pi-ai";

export default function (pi) {
  const { QABRO_SAKAI_BRIDGE, QABRO_SAKAI_TOKEN, QABRO_SAKAI_TURNS } = process.env;
  let turns = 0;
  pi.on("turn_start", (_event, ctx) => {
    if (++turns > Number(QABRO_SAKAI_TURNS)) ctx.abort();
  });
  pi.registerTool({
    name: "sakai", label: "Sakai CRUD",
    description: "Read the offered skill, inspect visible Sakai controls, or perform it with a selector.",
    parameters: Type.Object({
      action: StringEnum(["inspect", "click", "fill", "read_skill"]),
      selector: Type.Optional(Type.String()),
    }, { additionalProperties: false }),
    async execute(_id, args, signal) {
      const response = await fetch(QABRO_SAKAI_BRIDGE, {
        method: "POST", headers: { Authorization: "Bearer " + QABRO_SAKAI_TOKEN },
        body: JSON.stringify(args), signal,
      });
      const text = await response.text();
      const completion = response.ok && JSON.parse(text).status === "creation_complete";
      return { content: [{ type: "text", text }], terminate: completion };
    },
  });
}
