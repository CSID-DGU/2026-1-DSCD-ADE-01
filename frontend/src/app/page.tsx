import { UploadPageClient } from "@/components/upload/UploadPageClient";
import { recentDocuments } from "@/data/mockContract";

export default function HomePage() {
  return <UploadPageClient documents={recentDocuments} />;
}
