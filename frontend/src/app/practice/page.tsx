import { PracticeView } from "@/components/practice/practice-view";

export const metadata = {
  title: "Practice - SAT AI Tutor",
};

type PracticePageProps = {
  searchParams?:
    | {
        autoResume?: string;
        sourceId?: string;
        draftId?: string;
        preview?: string;
      }
    | Promise<{
        autoResume?: string;
        sourceId?: string;
        draftId?: string;
        preview?: string;
      }>;
};

export default async function PracticePage({ searchParams }: PracticePageProps = {}) {
  const resolvedParams = await searchParams;
  const autoResumeDiagnostic = resolvedParams?.autoResume === "diagnostic";
  const sourceIdParam = resolvedParams?.sourceId;
  const sourceId = sourceIdParam ? Number(sourceIdParam) : undefined;
  const draftIdParam = resolvedParams?.draftId;
  const draftId = draftIdParam ? Number(draftIdParam) : undefined;
  const isPreview = resolvedParams?.preview === "1" || resolvedParams?.preview === "true";
  return (
    <PracticeView
      autoResumeDiagnostic={autoResumeDiagnostic}
      sourceId={Number.isFinite(sourceId) ? sourceId : undefined}
      draftId={isPreview && Number.isFinite(draftId) ? draftId : undefined}
    />
  );
}

