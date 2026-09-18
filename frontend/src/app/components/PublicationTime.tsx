import type { Publication } from "@/lib/api";

export default function PublicationTime({ data }: { data: Publication | null }) {
  if (!data?.published_at) return null;
  return <p className="qualification-legend">Результаты опубликованы: <time dateTime={data.published_at}>{new Date(data.published_at).toLocaleString("ru-RU")}</time></p>;
}
