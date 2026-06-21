import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

export default function PageShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-zinc-950">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <TopBar title={title} />
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
