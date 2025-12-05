import { PracticeView } from "@/components/practice/practice-view";

export const metadata = {
  title: "Practice - SAT AI Tutor",
};

type PracticePageProps = {
  searchParams?:
    | {
        autoResume?: string;
      }
    | Promise<{
        autoResume?: string;
      }>;
};

export default async function PracticePage({ searchParams }: PracticePageProps = {}) {
  const resolvedParams = await searchParams;
  const autoResumeDiagnostic = resolvedParams?.autoResume === "diagnostic";
  return <PracticeView autoResumeDiagnostic={autoResumeDiagnostic} />;
}

