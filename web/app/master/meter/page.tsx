import { MasterPage, type MasterPageConfig } from "../_components/master-page";

const config: MasterPageConfig = {
  tableCode: "meter",
  title: "電號管理",
  description: "維護電號、顯示名稱、管理類型與備註。",
  fields: [
    { key: "electricity_code", label: "電號", required: true },
    { key: "name", label: "名稱" },
    { key: "management_type", label: "管理類型" },
    { key: "note", label: "備註" },
  ],
};

export default function MeterMasterPage() {
  return <MasterPage config={config} />;
}
