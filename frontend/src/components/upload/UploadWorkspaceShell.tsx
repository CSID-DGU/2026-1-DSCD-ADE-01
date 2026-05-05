import type { ReactNode } from "react";

type UploadWorkspaceShellProps = {
  children: ReactNode;
};

/**
 * 업로드/챗봇 탭 전환 시 동일한 카드 크기·위치를 유지하기 위한 공통 껍데기.
 */
export function UploadWorkspaceShell({ children }: UploadWorkspaceShellProps) {
  return (
    <div className="flex min-h-[520px] w-full min-w-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-dashed border-border-default bg-white p-8 shadow-sm sm:p-10">
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      </div>
    </div>
  );
}
