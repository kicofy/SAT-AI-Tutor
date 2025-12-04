import { useI18n } from "@/hooks/use-i18n";

type Props = {
  highlights: string[];
};

export function AIHighlights({ highlights }: Props) {
  const { t } = useI18n();
  if (!highlights.length) {
    return <p className="text-sm text-white/40">{t("ai.empty")}</p>;
  }
  return (
    <ul className="space-y-3 text-sm text-white/80">
      {highlights.map((highlight) => (
        <li
          key={highlight}
          className="rounded-xl border border-white/10 px-4 py-3 leading-relaxed"
        >
          {highlight}
        </li>
      ))}
    </ul>
  );
}

