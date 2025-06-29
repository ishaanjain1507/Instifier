export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-4xl font-bold">Welcome to Instifier</h1>
      <p className="mt-4">Please <a href="/auth/login" className="text-blue-500">Login</a> or <a href="/auth/signup" className="text-blue-500">Sign Up</a></p>
    </main>
  );
}