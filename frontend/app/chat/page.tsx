import Chat from '@/components/Chat'
export default function ChatPage() {
 return (
  <main className="min-h-screen bg-gray-50 p-4">
   <div className="mx-auto max-w-3xl">
    <header className="mb-4 flex items-center justify-between">
     <h1 className="text-xl font-bold">گفتگو</h1>
    </header>
    <Chat user_id={1} />
   </div>
  </main>
 )
}
