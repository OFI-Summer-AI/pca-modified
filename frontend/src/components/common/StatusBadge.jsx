export default function StatusBadge({ status, large }) {
  return (
    <span className={`badge ${status}${large ? ' lg' : ''}`}>
      {status}
    </span>
  );
}
