export default function RiskBadge({ risk, large }) {
  return (
    <span className={`badge ${risk}${large ? ' lg' : ''}`}>
      {risk}
    </span>
  );
}
