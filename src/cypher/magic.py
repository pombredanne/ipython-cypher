#!/usr/bin/env python
import re
from IPython.core.magic import (Magics, magics_class, cell_magic, line_magic,
                                needs_local_scope)
from IPython.config.configurable import Configurable
from IPython.utils.traitlets import Bool, Int, Unicode
try:
    from pandas.core.frame import DataFrame, Series
except ImportError:
    DataFrame = None
    Series = None

from neo4jrestclient.exceptions import StatusException

from cypher.connection import Connection
from cypher.parse import parse
from cypher.run import run


@magics_class
class CypherMagic(Magics, Configurable):
    """Runs Cypher statement on a database, specified by a connect string.

    Provides the %%cypher magic."""

    auto_limit = Int(0, config=True, help="""
        Automatically limit the size of the returned result sets
    """)
    style = Unicode('DEFAULT', config=True, help="""
        Set the table printing style to any of prettytable's defined styles
        (currently DEFAULT, MSWORD_FRIENDLY, PLAIN_COLUMNS, RANDOM)
    """)
    short_errors = Bool(True, config=True, help="""
        Don't display the full traceback on Neo4j errors
    """)
    data_contents = Bool(True, config=True, help="""
        Bring extra data to render the results as a graph
    """)
    display_limit = Int(0, config=True, help="""
        Automatically limit the number of rows displayed
        (full result set is still stored)
    """)
    auto_pandas = Bool(False, config=True, help="""
        Return Pandas DataFrame instead of regular result sets
    """)
    auto_html = Bool(False, config=True, help="""
        Return a D3 representation of the graph instead of regular result sets
    """)
    auto_networkx = Bool(False, config=True, help="""
        Return Networkx MultiDiGraph instead of regular result sets
    """)
    rest = Bool(False, config=True, help="""
        Return full REST representations of objects inside the result sets
    """)
    feedback = Bool(True, config=True, help="Print number of rows affected")
    legal_cypher_identifier = re.compile(r'^[A-Za-z0-9#_$]+')

    def __init__(self, shell):
        Configurable.__init__(self, config=shell.config)
        Magics.__init__(self, shell=shell)
        # Add ourself to the list of module configurable via %config
        self.shell.configurables.append(self)

    @needs_local_scope
    @line_magic('cypher')
    @cell_magic('cypher')
    def execute(self, line, cell='', local_ns={}):
        """Runs Cypher statement against a Neo4j graph database, specified by
        a connect string.

        If no database connection has been established, first word
        should be a connection string, or the user@host name
        of an established connection. Otherwise, http://localhost:7474/db/data
        will be assumed.

        Examples::

          %%cypher https://me:mypw@myhost:7474/db/data
          START n=node(*) RETURN n

          %%sql me@myhost
          START n=node(*) RETURN n

          %%sql
          START n=node(*) RETURN n

        Connect string syntax examples:

          http://localhost:7474/db/data
          https://me:mypw@localhost:7474/db/data

        """
        # save globals and locals so they can be referenced in bind vars
        user_ns = self.shell.user_ns
        user_ns.update(local_ns)
        parsed = parse("""{0}\n{1}""".format(line, cell), self)
        conn = Connection.get(parsed['uri'])
        first_word = parsed['cypher'].split(None, 1)[:1]
        if first_word and first_word[0].lower() == 'persist':
            return self._persist_dataframe(parsed['cypher'], conn, user_ns)
        try:
            result = run(conn, parsed['cypher'], self, user_ns)
            return result
        except StatusException as e:
            if self.short_errors:
                print(e)
            else:
                raise

    def _persist_dataframe(self, raw, conn, user_ns):
        if not DataFrame:
            raise ImportError("Must `pip install pandas` to use DataFrames")
        pieces = raw.split()
        if len(pieces) != 2:
            raise SyntaxError(
                "Format: %cypher [connection] persist <DataFrameName>"
            )
        frame_name = pieces[1].strip(';')
        frame = eval(frame_name, user_ns)
        if not isinstance(frame, DataFrame) and not isinstance(frame, Series):
            raise TypeError(
                '%s is not a Pandas DataFrame or Series' % frame_name
            )
        table_name = frame_name.lower()
        table_name = self.legal_cypher_identifier.search(table_name).group(0)
        frame.to_sql(table_name, conn.session.engine)
        return 'Persisted %s' % table_name


def load_ipython_extension(ip):
    """Load the extension in IPython."""
    ip.register_magics(CypherMagic)
