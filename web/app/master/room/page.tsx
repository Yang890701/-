import { MasterPage, type MasterPageConfig } from "../_components/master-page";

const config: MasterPageConfig = {
  tableCode: "room",
  title: "房號管理",
  description: "維護房號、所屬案場、電號關聯與計費管理資訊。",
  fields: [
    { key: "site_id", label: "案場ID", type: "number", required: true },
    { key: "room_code", label: "房號", required: true },
    { key: "room_name", label: "房名" },
    { key: "meter_id", label: "電號ID", type: "number" },
    { key: "management_type", label: "管理類型" },
    { key: "management_contact", label: "管理聯絡" },
    { key: "billing_mode", label: "計費模式" },
  ],
};

export default function RoomMasterPage() {
  return <MasterPage config={config} />;
}
