import asyncio
import json
import logging
#logging.basicConfig(level=logging.INFO)

async def read_exactly_async(reader, n: int) -> bytes:
    """Async: Read exactly n bytes from a StreamReader."""
    chunks = []
    remaining = n

    while remaining > 0:
        #chunk = await reader.read(remaining)   # <-- FIXED
        try:
            chunk = await asyncio.wait_for(reader.read(remaining), timeout=5.0)
        except asyncio.TimeoutError:
            print("Read timed out!")
            chunk = None


        if not chunk:
            raise EOFError(
                f"Expected {n} bytes, but stream ended early "
                f"(received {n - remaining})"
            )
            return b""

        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


async def send_stop_command(mode: str, path_config: str, reader, writer) -> None:
    """Send a start command to the appropriate UNIX socket."""

    with open(path_config, 'r') as f:
        path = json.load(f)

    if mode in ("hwsim", "test"):
        socket_path = path["command"]["hwsim"]
    elif mode == "real":
        socket_path = path["command"]["real"]
    else:
        raise ValueError(f"Invalid mode: {mode}")

    #writer = None
    try:
        #reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write(bytes([0x1, 0x0, 0x0, 0x0, 0x1]))
        await writer.drain()

        logging.debug("[start_stop][quantum channel] Stop Command sent")
        response = await read_exactly_async(reader, 5)
        logging.debug(f"[start_stop][quantum channel] Stop Command response: {list(response)}")

    except BrokenPipeError as e:
        # If the server closed its side, log the error but treat it as a successful shutdown
        logging.warning(f"[start_stop][quantum channel] BrokenPipeError while sending stop command. Server connection was already closed: {e}")

    except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
        # Handles connection issues other than Broken Pipe (server not started, socket missing, etc.)
        logging.error(f"[start_stop][quantum channel] Failed to send stop command: {e} with socket {socket_path}")

    finally:
        # Close the writer regardless of whether communication succeeded
        if writer is not None:
            logging.debug("[start_stop][quantum channel] Closing writer and waiting for closure.")
            writer.close()
            try:
                # Add a timeout to prevent potential hanging if the socket is truly corrupted
                await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                logging.warning("[start_stop][quantum channel] Timeout while waiting for writer to close. Proceeding.")
            except Exception as e:
                # Catch any unexpected errors during final closure, including potential lingering BrokenPipe issues
                logging.warning(f"[start_stop][quantum channel] Error during final writer cleanup: {e}")


async def send_start_command(mode: str, path_config: str):
    """Send a start command to the appropriate UNIX socket and return reader, writer."""

    with open(path_config, 'r') as f:
        path = json.load(f)

    if mode in ("hwsim", "test"):
        socket_path = path["command"]["hwsim"]
    elif mode == "real":
        socket_path = path["command"]["real"]
    else:
        raise ValueError(f"Invalid mode: {mode}")

    reader = None
    writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write(bytes([0x1, 0x0, 0x0, 0x0, 0x0]))
        await writer.drain()

        logging.debug("[start_stop][quantum channel] Start Command sent")
        response = await read_exactly_async(reader, 5)
        logging.debug(f"[start_stop][quantum channel] Got response: {list(response)}")
        
        return reader, writer

    except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
        logging.error(f"[start_stop][quantum channel] Failed to send start command: {e} with socket {socket_path}")
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        return None, None





def main():
    asyncio.run(send_start_command("hwsim"))


if __name__ == "__main__":
    main()